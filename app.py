#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Crawler PDF V2.0 - Sistema Avançado para QGC
=============================================
Versão profissional com cache, otimizações e detecção inteligente
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
from fuzzywuzzy import fuzz
from flask import Flask, render_template_string, request, jsonify, send_file
import threading
import re
from typing import Dict, List, Optional

class QGCAnalyzer:
    """Analisador especializado para Quadro Geral de Credores"""
    
    def __init__(self):
        self.qgc_indicators = [
            'quadro geral de credores', 'qgc', 'relação de credores',
            'credores quirografários', 'credores trabalhistas',
            'credores com garantia real', 'administrador judicial'
        ]
        
        self.value_pattern = r'R\$\s*([\d.,]+(?:\.\d{2})?)'
        self.cnpj_pattern = r'\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}'
    
    def detect_document_type(self, text: str) -> Dict:
        """Detecta tipo de documento"""
        text_lower = text.lower()
        
        qgc_score = sum(1 for indicator in self.qgc_indicators if indicator in text_lower)
        
        if qgc_score >= 2:
            return {
                'type': 'qgc',
                'confidence': min(90, qgc_score * 30),
                'values_found': len(re.findall(self.value_pattern, text)),
                'cnpjs_found': len(re.findall(self.cnpj_pattern, text))
            }
        
        return {
            'type': 'unknown',
            'confidence': 0,
            'values_found': 0,
            'cnpjs_found': 0
        }

class CacheManager:
    """Sistema de cache simples para PDFs"""
    
    def __init__(self):
        self.cache = {}
    
    def get_file_hash(self, file_path: str) -> str:
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    
    def get_cached_content(self, file_hash: str):
        return self.cache.get(file_hash)
    
    def cache_content(self, file_hash: str, content: Dict):
        self.cache[file_hash] = content

class AdvancedMatcher:
    """Sistema de correspondência avançado"""
    
    def __init__(self):
        self.common_words = {
            'ltda', 'sa', 'cia', 'inc', 'corp', 'limited', 'tech', 'group', 
            'international', 'brasil', 'brazil', 'company', 'solutions', 
            'services', 'industria', 'comercio', 'global', 'nacional'
        }
        
        self.qgc_analyzer = QGCAnalyzer()
    
    def advanced_search(self, client_name: str, text: str, threshold: int) -> Dict:
        """Busca avançada com múltiplos algoritmos"""
        
        # 1. Busca exata
        if client_name.lower() in text.lower():
            context = self._extract_context(client_name, text)
            extracted_data = self._extract_client_data(client_name, text)
            
            return {
                'found': True,
                'confidence': 95,
                'match_type': 'Exata',
                'context': context,
                'extracted_data': extracted_data
            }
        
        # 2. Busca por palavras significativas
        words = re.findall(r'\w+', client_name.lower())
        significant_words = [w for w in words if len(w) >= 3 and w not in self.common_words]
        
        if significant_words:
            found_words = [w for w in significant_words if w in text.lower()]
            
            if len(found_words) >= 2 and len(found_words) / len(significant_words) >= 0.8:
                context = self._extract_context(found_words[0], text)
                confidence = int((len(found_words) / len(significant_words)) * 90)
                extracted_data = self._extract_client_data(client_name, text)
                
                return {
                    'found': True,
                    'confidence': confidence,
                    'match_type': f'Palavras ({len(found_words)}/{len(significant_words)})',
                    'context': context,
                    'extracted_data': extracted_data
                }
        
        # 3. Busca fuzzy rigorosa
        similarity = fuzz.partial_ratio(client_name.lower(), text.lower())
        if similarity >= max(threshold, 88):  # Mínimo 88%
            context = self._extract_context(client_name, text)
            extracted_data = self._extract_client_data(client_name, text)
            
            return {
                'found': True,
                'confidence': similarity,
                'match_type': f'Fuzzy ({similarity}%)',
                'context': context,
                'extracted_data': extracted_data
            }
        
        return {
            'found': False,
            'confidence': similarity,
            'match_type': 'Não encontrado',
            'context': '',
            'extracted_data': {}
        }
    
    def _extract_context(self, search_term: str, text: str, size: int = 200) -> str:
        """Extrai contexto ao redor do termo"""
        index = text.lower().find(search_term.lower())
        if index != -1:
            start = max(0, index - size // 2)
            end = min(len(text), index + len(search_term) + size // 2)
            return text[start:end].strip()
        return ""
    
    def _extract_client_data(self, client_name: str, text: str) -> Dict:
        """Extrai dados específicos do cliente"""
        context = self._extract_context(client_name, text, 400)
        
        values = re.findall(self.qgc_analyzer.value_pattern, context)
        cnpjs = re.findall(self.qgc_analyzer.cnpj_pattern, context)
        
        return {
            'values': values[:3],  # Máximo 3 valores
            'cnpjs': cnpjs[:2],    # Máximo 2 CNPJs
        }

class CrawlerPDFV2:
    """Crawler PDF Versão 2.0"""
    
    def __init__(self):
        self.threshold = 80
        self.results = []
        self.processing = False
        self.cancelled = False
        self.progress = 0
        self.status_message = "Pronto para processar"
        self.last_output_file = None
        self.last_output_filename = None
        
        self.cache_manager = CacheManager()
        self.matcher = AdvancedMatcher()
        self.qgc_analyzer = QGCAnalyzer()
        
        self.stats = {
            'processing_start': None,
            'total_clients': 0,
            'found_clients': 0
        }
    
    def reset_processing(self):
        """Reseta estado"""
        self.cancelled = False
        self.processing = False
        self.progress = 0
        self.results = []
        self.status_message = "Pronto para processar"
    
    def cancel_processing(self):
        """Cancela processamento"""
        self.cancelled = True
        self.status_message = "❌ Processamento cancelado"
        self.processing = False
    
    def read_excel_clients(self, excel_path: str) -> List[str]:
        """Lê clientes do Excel"""
        try:
            df = pd.read_excel(excel_path)
            if df.empty:
                return []
            
            clients = df.iloc[:, 0].dropna().astype(str).tolist()
            return [client.strip() for client in clients if client.strip()]
            
        except Exception as e:
            raise Exception(f"Erro ao ler Excel: {str(e)}")
    
    def read_pdf_optimized(self, pdf_path: str) -> Dict:
        """Lê PDF com cache e otimizações"""
        file_hash = self.cache_manager.get_file_hash(pdf_path)
        
        # Verificar cache
        cached = self.cache_manager.get_cached_content(file_hash)
        if cached:
            self.status_message = "📋 Conteúdo recuperado do cache"
            return cached
        
        try:
            text = ""
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                total_pages = len(reader.pages)
                
                for i, page in enumerate(reader.pages):
                    self.progress = int((i / total_pages) * 30)  # 0-30% para leitura
                    self.status_message = f"📄 Processando página {i+1}/{total_pages}"
                    
                    text += page.extract_text() + "\n\n"
                    
                    if self.cancelled:
                        return None
            
            # Análise do documento
            doc_analysis = self.qgc_analyzer.detect_document_type(text)
            
            result = {
                'text': text,
                'analysis': doc_analysis,
                'total_pages': total_pages,
                'total_chars': len(text)
            }
            
            # Salvar no cache
            self.cache_manager.cache_content(file_hash, result)
            
            return result
            
        except Exception as e:
            raise Exception(f"Erro ao processar PDF: {str(e)}")
    
    def process_files_v2(self, excel_path: str, pdf_path: str, threshold: int):
        """Processamento principal V2.0"""
        
        try:
            self.reset_processing()
            self.processing = True
            self.threshold = threshold
            self.stats['processing_start'] = time.time()
            
            # 1. Ler Excel
            self.progress = 5
            self.status_message = "📊 Lendo arquivo Excel..."
            clients = self.read_excel_clients(excel_path)
            
            if not clients:
                self.status_message = "❌ Nenhum cliente encontrado"
                self.processing = False
                return None
            
            self.stats['total_clients'] = len(clients)
            
            # 2. Processar PDF
            self.progress = 10
            self.status_message = "📄 Processando PDF..."
            pdf_content = self.read_pdf_optimized(pdf_path)
            
            if self.cancelled or not pdf_content:
                return None
            
            # 3. Informar tipo de documento
            doc_type = pdf_content['analysis']['type']
            confidence = pdf_content['analysis']['confidence']
            self.status_message = f"🔍 Documento: {doc_type} (confiança: {confidence}%)"
            
            # 4. Buscar correspondências
            results = []
            for i, client in enumerate(clients):
                if self.cancelled:
                    break
                
                self.progress = 30 + int((i / len(clients)) * 60)  # 30-90%
                self.status_message = f"🔍 Buscando: {client} ({i+1}/{len(clients)})"
                
                match_result = self.matcher.advanced_search(client, pdf_content['text'], threshold)
                
                if match_result['found']:
                    self.stats['found_clients'] += 1
                
                results.append({
                    'cliente': client,
                    'encontrado': 'Sim' if match_result['found'] else 'Não',
                    'confianca': f"{match_result['confidence']}%",
                    'tipo_match': match_result['match_type'],
                    'valores_encontrados': ', '.join(match_result['extracted_data'].get('values', [])),
                    'cnpjs_encontrados': ', '.join(match_result['extracted_data'].get('cnpjs', [])),
                    'contexto': match_result['context'][:150] + '...' if len(match_result['context']) > 150 else match_result['context']
                })
                
                time.sleep(0.01)  # Permite cancelamento
            
            if self.cancelled:
                return None
            
            # 5. Salvar resultados
            self.progress = 95
            self.status_message = "💾 Salvando resultados..."
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"crawler_v2_{timestamp}.xlsx"
            output_path = os.path.join(tempfile.gettempdir(), output_filename)
            
            # Criar DataFrame com resultados
            df = pd.DataFrame(results)
            
            # Adicionar aba de estatísticas
            stats_data = {
                'Métrica': [
                    'Total de Clientes',
                    'Clientes Encontrados', 
                    'Taxa de Sucesso (%)',
                    'Tipo de Documento',
                    'Confiança na Detecção (%)',
                    'Páginas Processadas',
                    'Valores Monetários no PDF',
                    'CNPJs no PDF'
                ],
                'Valor': [
                    len(results),
                    self.stats['found_clients'],
                    f"{(self.stats['found_clients'] / len(results) * 100):.1f}%",
                    pdf_content['analysis']['type'],
                    pdf_content['analysis']['confidence'],
                    pdf_content['total_pages'],
                    pdf_content['analysis']['values_found'],
                    pdf_content['analysis']['cnpjs_found']
                ]
            }
            df_stats = pd.DataFrame(stats_data)
            
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Resultados', index=False)
                df_stats.to_excel(writer, sheet_name='Análise do Documento', index=False)
            
            # Finalizar
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
                'document_analysis': pdf_content['analysis'],
                'processing_time': processing_time
            }
            
        except Exception as e:
            self.status_message = f"❌ Erro: {str(e)}"
            self.processing = False
            return None

# Instância global
crawler_v2 = CrawlerPDFV2()

# Flask App
app = Flask(__name__)
app.secret_key = 'crawler_v2_secret'

@app.route('/')
def index():
    """Página principal V2.0"""
    with open('template_v2.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/process_v2', methods=['POST'])
def process_files_v2():
    """Processamento V2.0"""
    try:
        excel_file = request.files.get('excelFile')
        pdf_file = request.files.get('pdfFile')
        tolerance = request.form.get('tolerance')
        
        if not excel_file or not pdf_file:
            return jsonify({'success': False, 'error': 'Arquivos não enviados'}), 400
        
        threshold = int(tolerance)
        
        # Salvar arquivos temporários
        temp_dir = tempfile.mkdtemp()
        excel_path = os.path.join(temp_dir, f"excel_{excel_file.filename}")
        pdf_path = os.path.join(temp_dir, f"pdf_{pdf_file.filename}")
        
        excel_file.save(excel_path)
        pdf_file.save(pdf_path)
        
        # Processar em thread separada
        def process_thread():
            result = crawler_v2.process_files_v2(excel_path, pdf_path, threshold)
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/progress_v2')
def get_progress_v2():
    """Progresso V2.0 com estatísticas"""
    if not crawler_v2.processing and crawler_v2.results:
        return jsonify({
            'processing': False,
            'progress': 100,
            'status': crawler_v2.status_message,
            'results': {
                'total': len(crawler_v2.results),
                'found': crawler_v2.stats['found_clients'],
                'file': crawler_v2.last_output_filename,
                'processing_time': f"{time.time() - crawler_v2.stats['processing_start']:.1f}"
            },
            'document_analysis': getattr(crawler_v2, 'document_analysis', None)
        })
    else:
        return jsonify({
            'processing': crawler_v2.processing,
            'progress': crawler_v2.progress,
            'status': crawler_v2.status_message,
            'stats': crawler_v2.stats,
            'document_analysis': getattr(crawler_v2, 'document_analysis', None)
        })

@app.route('/cancel', methods=['POST'])
def cancel_processing():
    """Cancelar processamento"""
    try:
        crawler_v2.cancel_processing()
        return jsonify({'success': True, 'message': 'Processamento cancelado'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download de resultados"""
    try:
        if crawler_v2.last_output_file and os.path.exists(crawler_v2.last_output_file):
            return send_file(crawler_v2.last_output_file, as_attachment=True, download_name=filename)
        else:
            return "Arquivo não encontrado", 404
    except Exception as e:
        return f"Erro ao baixar: {e}", 500

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 