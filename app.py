#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Crawler PDF V3.0 - Matching Robusto para QGC
=============================================
Versão com normalização pesada e fuzzy matching otimizado
"""

import os
import tempfile
import shutil
import hashlib
import json
import time
from datetime import datetime
import pandas as pd
import PyPDF2
import unidecode
from rapidfuzz import fuzz
from flask import Flask, render_template_string, request, jsonify, send_file
import threading
import re

# ----------- Funções de Normalização e Aliases -----------

COMMON_WORDS = {
    'sa', 's.a', 'ltda', 'eireli', 'me', 'empresa', 'cia', 'industria', 'comercio',
    'do', 'da', 'de', 'dos', 'das', 'the', 'inc', 'corp', 'co', 'group', 'solutions',
    'holding', 'brasil', 'brazil', 'financeira', 'banco', 'administradora', 'servicos', 'serviços'
}

def normalize_name(name):
    """Remove acentos, pontuação, termos genéricos e coloca tudo minúsculo"""
    name = unidecode.unidecode(name)  # Remove acentos
    name = name.lower()
    name = re.sub(r'[^\w\s]', '', name)  # Remove pontuação
    words = [w for w in name.split() if w not in COMMON_WORDS and len(w) > 2]
    return ' '.join(words)

def generate_aliases(name):
    """Gera possíveis aliases removendo partes menos relevantes"""
    base = normalize_name(name)
    tokens = base.split()
    aliases = set()
    for i in range(len(tokens)):
        for j in range(i+1, len(tokens)+1):
            alias = ' '.join(tokens[i:j])
            if len(alias) >= 3:
                aliases.add(alias)
    aliases.add(base)  # garante o nome completo também
    return aliases

def match_client_in_text(client_name, text, min_threshold=80):
    text_normalized = normalize_name(text)
    aliases = generate_aliases(client_name)
    melhor_score = 0
    melhor_alias = ''
    melhor_contexto = ''
    for alias in aliases:
        if not alias or len(alias) < 3:
            continue
        score = fuzz.partial_ratio(alias, text_normalized)
        if score > melhor_score:
            melhor_score = score
            melhor_alias = alias
            idx = text_normalized.find(alias)
            if idx >= 0:
                start = max(0, idx-100)
                end = min(len(text), idx+len(alias)+100)
                melhor_contexto = text[start:end]
        if melhor_score >= 95:
            break
    found = melhor_score >= min_threshold
    return {
        'found': found,
        'confidence': melhor_score,
        'alias': melhor_alias,
        'context': melhor_contexto.strip()
    }

# -------------- Classe principal --------------

class CrawlerPDFV3:
    def __init__(self):
        self.threshold = 80
        self.results = []
        self.processing = False
        self.cancelled = False
        self.progress = 0
        self.status_message = "Pronto para processar"
        self.last_output_file = None
        self.last_output_filename = None
        self.stats = {
            'processing_start': None,
            'total_clients': 0,
            'found_clients': 0
        }

    def reset_processing(self):
        self.cancelled = False
        self.processing = False
        self.progress = 0
        self.results = []
        self.status_message = "Pronto para processar"
        self.stats['found_clients'] = 0

    def cancel_processing(self):
        self.cancelled = True
        self.status_message = "❌ Processamento cancelado"
        self.processing = False

    def read_excel_clients(self, excel_path: str):
        df = pd.read_excel(excel_path)
        if df.empty:
            return []
        clients = df.iloc[:, 0].dropna().astype(str).tolist()
        return [client.strip() for client in clients if client.strip()]

    def read_pdf(self, pdf_path: str):
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            total_pages = len(reader.pages)
            for i, page in enumerate(reader.pages):
                self.progress = int((i / total_pages) * 30)  # 0-30% para leitura
                self.status_message = f"📄 Processando página {i+1}/{total_pages}"
                text += page.extract_text() or ""
                if self.cancelled:
                    return None
        return text

    def process_files(self, excel_path, pdf_path, threshold):
        try:
            self.reset_processing()
            self.processing = True
            self.threshold = threshold
            self.stats['processing_start'] = time.time()
            self.status_message = "📊 Lendo arquivo Excel..."
            self.progress = 5
            clients = self.read_excel_clients(excel_path)
            if not clients:
                self.status_message = "❌ Nenhum cliente encontrado"
                self.processing = False
                return None
            self.stats['total_clients'] = len(clients)

            self.status_message = "📄 Processando PDF..."
            self.progress = 10
            pdf_text = self.read_pdf(pdf_path)
            if self.cancelled or not pdf_text:
                return None

            results = []
            for i, client in enumerate(clients):
                if self.cancelled:
                    break
                self.progress = 30 + int((i / len(clients)) * 60)  # 30-90%
                self.status_message = f"🔍 Buscando: {client} ({i+1}/{len(clients)})"
                match_result = match_client_in_text(client, pdf_text, threshold)
                if match_result['found']:
                    self.stats['found_clients'] += 1
                results.append({
                    'cliente': client,
                    'encontrado': 'Sim' if match_result['found'] else 'Não',
                    'confianca': f"{match_result['confidence']}%",
                    'alias_usado': match_result['alias'],
                    'contexto': match_result['context'][:150] + '...' if len(match_result['context']) > 150 else match_result['context']
                })
                time.sleep(0.01)

            if self.cancelled:
                return None

            self.progress = 95
            self.status_message = "💾 Salvando resultados..."
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"crawler_v3_{timestamp}.xlsx"
            output_path = os.path.join(tempfile.gettempdir(), output_filename)
            df = pd.DataFrame(results)

            stats_data = {
                'Métrica': [
                    'Total de Clientes',
                    'Clientes Encontrados',
                    'Taxa de Sucesso (%)'
                ],
                'Valor': [
                    len(results),
                    self.stats['found_clients'],
                    f"{(self.stats['found_clients'] / len(results) * 100):.1f}%"
                ]
            }
            df_stats = pd.DataFrame(stats_data)

            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Resultados', index=False)
                df_stats.to_excel(writer, sheet_name='Estatísticas', index=False)

            self.results = results
            self.processing = False
            self.last_output_file = output_path
            self.last_output_filename = output_filename

            processing_time = time.time() - self.stats['processing_start']
            self.status_message = f"✅ Concluído! {self.stats['found_clients']}/{len(results)} encontrados em {processing_time:.1f}s"
            self.progress = 100

            return {
                'success': True,
                'total': len(results),
                'found': self.stats['found_clients'],
                'file': output_filename,
                'results': results,
                'processing_time': processing_time
            }
        except Exception as e:
            self.status_message = f"❌ Erro: {str(e)}"
            self.processing = False
            return None

# ------------ Flask app ------------

crawler_v3 = CrawlerPDFV3()
app = Flask(__name__)
app.secret_key = 'crawler_v3_secret'

@app.route('/')
def index():
    return """
    <h1>Crawler PDF V3</h1>
    <form action="/process_v3" method="post" enctype="multipart/form-data">
        Excel: <input type="file" name="excelFile"><br>
        PDF: <input type="file" name="pdfFile"><br>
        Tolerância (padrão 80): <input type="number" name="tolerance" value="80"><br>
        <input type="submit" value="Processar">
    </form>
    """

@app.route('/process_v3', methods=['POST'])
def process_files_v3():
    try:
        excel_file = request.files.get('excelFile')
        pdf_file = request.files.get('pdfFile')
        tolerance = request.form.get('tolerance', 80)
        if not excel_file or not pdf_file:
            return jsonify({'success': False, 'error': 'Arquivos não enviados'}), 400
        threshold = int(tolerance)
        temp_dir = tempfile.mkdtemp()
        excel_path = os.path.join(temp_dir, f"excel_{excel_file.filename}")
        pdf_path = os.path.join(temp_dir, f"pdf_{pdf_file.filename}")
        excel_file.save(excel_path)
        pdf_file.save(pdf_path)
        def process_thread():
            crawler_v3.process_files(excel_path, pdf_path, threshold)
            shutil.rmtree(temp_dir, ignore_errors=True)
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/progress_v3')
def get_progress_v3():
    if not crawler_v3.processing and crawler_v3.results:
        return jsonify({
            'processing': False,
            'progress': 100,
            'status': crawler_v3.status_message,
            'results': {
                'total': len(crawler_v3.results),
                'found': crawler_v3.stats['found_clients'],
                'file': crawler_v3.last_output_filename,
                'processing_time': f"{time.time() - crawler_v3.stats['processing_start']:.1f}"
            }
        })
    else:
        return jsonify({
            'processing': crawler_v3.processing,
            'progress': crawler_v3.progress,
            'status': crawler_v3.status_message,
            'stats': crawler_v3.stats
        })

@app.route('/cancel', methods=['POST'])
def cancel_processing():
    try:
        crawler_v3.cancel_processing()
        return jsonify({'success': True, 'message': 'Processamento cancelado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        if crawler_v3.last_output_file and os.path.exists(crawler_v3.last_output_file):
            return send_file(crawler_v3.last_output_file, as_attachment=True, download_name=filename)
        else:
            return "Arquivo não encontrado", 404
    except Exception as e:
        return f"Erro ao baixar: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
