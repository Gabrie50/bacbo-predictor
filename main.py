# main.py - VERSÃO COM SQLITE FALLBACK
# =============================================================================

import os
import sys
import time
import requests
import json
import urllib.parse
import threading
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import traceback

# =============================================================================
# 🔇 SILENCIAR AVISOS
# =============================================================================
import warnings
warnings.filterwarnings('ignore')
os.environ['PYTHONWARNINGS'] = 'ignore'

# =============================================================================
# 🚀 INICIAR FLASK
# =============================================================================
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# =============================================================================
# 🏥 HEALTHCHECK
# =============================================================================
@app.route('/health', methods=['GET'])
def health_urgente():
    return jsonify({
        'status': 'ok',
        'mensagem': 'Sistema Online',
        'timestamp': time.time(),
        'versao': '10.0',
        'total_rodadas': cache.get('leves', {}).get('total_rodadas', 0)
    })

@app.route('/', methods=['GET'])
def home_rapida():
    try:
        return render_template('index.html')
    except Exception as e:
        print(f"Erro ao renderizar index: {e}")
        return jsonify({'erro': 'Template não encontrado'}), 500

@app.route('/mapa-mental')
def mapa_mental():
    try:
        return render_template('mapa_mental.html')
    except Exception as e:
        return jsonify({'erro': 'Template não encontrado'}), 500

# =============================================================================
# TENTAR IMPORTAR ENSEMBLE
# =============================================================================
try:
    from app.ml.ensemble import EnsembleEvolutivo
    from app.ml.memory_map import MapaMental
    from app.ml.indicators import BacBoIndicators
    ML_AVAILABLE = True
    print("✅ ML modules carregados")
except Exception as e:
    print(f"⚠️ Erro ao carregar ML: {e}")
    ML_AVAILABLE = False

# =============================================================================
# CONFIGURAÇÕES - DATABASE (PostgreSQL ou SQLite)
# =============================================================================
USE_SQLITE = False
DB_CONNECTION = None

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if DATABASE_URL:
    try:
        import pg8000
        import ssl
        parsed = urllib.parse.urlparse(DATABASE_URL)
        DB_USER = parsed.username
        DB_PASSWORD = parsed.password
        DB_HOST = parsed.hostname
        DB_PORT = parsed.port or 5432
        DB_NAME = parsed.path[1:]
        SSL_CONTEXT = ssl.create_default_context()
        SSL_CONTEXT.check_hostname = False
        SSL_CONTEXT.verify_mode = ssl.CERT_NONE
        print("✅ Configurado para PostgreSQL")
    except:
        USE_SQLITE = True
        print("⚠️ PostgreSQL falhou, usando SQLite")
else:
    USE_SQLITE = True
    print("📁 Usando SQLite local")

# =============================================================================
# FUNÇÕES DE BANCO DE DADOS (PostgreSQL ou SQLite)
# =============================================================================

def get_db_connection():
    global DB_CONNECTION
    if USE_SQLITE:
        if DB_CONNECTION is None:
            DB_CONNECTION = sqlite3.connect('bacbo.db', check_same_thread=False)
            DB_CONNECTION.row_factory = sqlite3.Row
        return DB_CONNECTION
    else:
        try:
            import pg8000
            import ssl
            conn = pg8000.connect(
                user=DB_USER,
                password=DB_PASSWORD,
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                ssl_context=SSL_CONTEXT,
                timeout=30
            )
            return conn
        except Exception as e:
            print(f"⚠️ Erro PostgreSQL: {e}")
            return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível")
        return False
    try:
        cur = conn.cursor()
        
        if USE_SQLITE:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rodadas (
                    id TEXT PRIMARY KEY,
                    data_hora TIMESTAMP,
                    player_score INTEGER,
                    banker_score INTEGER,
                    soma INTEGER,
                    resultado TEXT,
                    fonte TEXT,
                    dados_json TEXT
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS historico_previsoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    previsao TEXT,
                    simbolo TEXT,
                    confianca INTEGER,
                    resultado_real TEXT,
                    acertou BOOLEAN,
                    estrategias TEXT,
                    modo TEXT,
                    total_agentes INTEGER,
                    geracao INTEGER
                )
            ''')
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rodadas (
                    id TEXT PRIMARY KEY,
                    data_hora TIMESTAMPTZ,
                    player_score INTEGER,
                    banker_score INTEGER,
                    soma INTEGER,
                    resultado TEXT,
                    fonte TEXT,
                    dados_json JSONB
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_data_hora ON rodadas(data_hora DESC)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_resultado ON rodadas(resultado)')
            
            cur.execute('''
                CREATE TABLE IF NOT EXISTS historico_previsoes (
                    id SERIAL PRIMARY KEY,
                    data_hora TIMESTAMPTZ DEFAULT NOW(),
                    previsao TEXT,
                    simbolo TEXT,
                    confianca INTEGER,
                    resultado_real TEXT,
                    acertou BOOLEAN,
                    estrategias TEXT,
                    modo TEXT,
                    total_agentes INTEGER,
                    geracao INTEGER
                )
            ''')
        
        conn.commit()
        cur.close()
        print(f"✅ Tabelas OK ({'SQLite' if USE_SQLITE else 'PostgreSQL'})")
        return True
    except Exception as e:
        print(f"❌ Erro tabelas: {e}")
        return False

def salvar_rodada(rodada, fonte):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        
        if USE_SQLITE:
            cur.execute('''
                INSERT OR IGNORE INTO rodadas 
                (id, data_hora, player_score, banker_score, soma, resultado, fonte, dados_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                rodada['id'],
                rodada['data_hora'],
                rodada['player_score'],
                rodada['banker_score'],
                rodada['player_score'] + rodada['banker_score'],
                rodada['resultado'],
                fonte,
                json.dumps(rodada, default=str)
            ))
        else:
            cur.execute('''
                INSERT INTO rodadas 
                (id, data_hora, player_score, banker_score, soma, resultado, fonte, dados_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            ''', (
                rodada['id'],
                rodada['data_hora'],
                rodada['player_score'],
                rodada['banker_score'],
                rodada['player_score'] + rodada['banker_score'],
                rodada['resultado'],
                fonte,
                json.dumps(rodada, default=str)
            ))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro salvar: {e}")
        return False

def salvar_previsao(previsao, resultado_real, acertou, total_agentes, geracao):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        
        estrategias_str = ','.join(previsao.get('estrategias', []))[:500]
        
        if USE_SQLITE:
            cur.execute('''
                INSERT INTO historico_previsoes 
                (data_hora, previsao, simbolo, confianca, resultado_real, acertou, 
                 estrategias, modo, total_agentes, geracao)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now(),
                previsao['previsao'],
                previsao.get('simbolo', '🔴' if previsao['previsao'] == 'BANKER' else '🔵'),
                previsao['confianca'],
                resultado_real,
                acertou,
                estrategias_str,
                previsao.get('modo', 'ENSEMBLE_EVOLUTIVO'),
                total_agentes,
                geracao
            ))
        else:
            cur.execute('''
                INSERT INTO historico_previsoes 
                (data_hora, previsao, simbolo, confianca, resultado_real, acertou, 
                 estrategias, modo, total_agentes, geracao)
                VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                previsao['previsao'],
                previsao.get('simbolo', '🔴' if previsao['previsao'] == 'BANKER' else '🔵'),
                previsao['confianca'],
                resultado_real,
                acertou,
                estrategias_str,
                previsao.get('modo', 'ENSEMBLE_EVOLUTIVO'),
                total_agentes,
                geracao
            ))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro salvar previsão: {e}")
        return False

# =============================================================================
# GERAR RODADAS DE TESTE
# =============================================================================

def gerar_rodada_teste():
    global ultimo_id_latest
    
    novo_id = f"teste_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    
    player_score = random.randint(2, 12)
    banker_score = random.randint(2, 12)
    
    if player_score > banker_score:
        resultado = 'PLAYER'
    elif banker_score > player_score:
        resultado = 'BANKER'
    else:
        resultado = 'TIE'
    
    rodada = {
        'id': novo_id,
        'data_hora': datetime.now(timezone.utc),
        'player_score': player_score,
        'banker_score': banker_score,
        'resultado': resultado
    }
    
    return rodada

# =============================================================================
# CARGA HISTÓRICA
# =============================================================================

def carregar_rodadas_passadas():
    print("\n" + "="*80)
    print("📥 CARREGANDO RODADAS")
    print("="*80)
    
    total = 0
    
    # Tentar API real
    try:
        API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo"
        HEADERS = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        params = {
            'page': 0,
            'size': 50,
            'sort': 'data.settledAt,desc',
            '_t': int(time.time() * 1000)
        }
        
        print("📡 Tentando API...", end=' ')
        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
        
        if response.status_code == 200:
            dados = response.json()
            if dados and len(dados) > 0:
                for item in dados[:30]:
                    try:
                        data = item.get('data', {})
                        result = data.get('result', {})
                        
                        player_dice = result.get('playerDice', {})
                        banker_dice = result.get('bankerDice', {})
                        player_score = player_dice.get('first', 0) + player_dice.get('second', 0)
                        banker_score = banker_dice.get('first', 0) + banker_dice.get('second', 0)
                        
                        outcome = result.get('outcome', '')
                        if outcome == 'PlayerWon':
                            resultado = 'PLAYER'
                        elif outcome == 'BankerWon':
                            resultado = 'BANKER'
                        else:
                            resultado = 'TIE'
                        
                        settled_at = data.get('settledAt', '')
                        if settled_at:
                            data_hora = datetime.fromisoformat(settled_at.replace('Z', '+00:00'))
                        else:
                            data_hora = datetime.now(timezone.utc)
                        
                        rodada = {
                            'id': data.get('id'),
                            'data_hora': data_hora,
                            'player_score': player_score,
                            'banker_score': banker_score,
                            'resultado': resultado
                        }
                        
                        if salvar_rodada(rodada, 'historico'):
                            total += 1
                            
                    except:
                        continue
                print(f"✅ {total} rodadas da API")
            else:
                print("⚠️ API sem dados")
        else:
            print(f"❌ Status {response.status_code}")
    except Exception as e:
        print(f"❌ API erro: {e}")
    
    # Gerar dados de teste se necessário
    if total < 30:
        print("📊 Gerando dados de teste...")
        for i in range(50):
            rodada = gerar_rodada_teste()
            if salvar_rodada(rodada, 'teste'):
                total += 1
                if (i + 1) % 10 == 0:
                    print(f"   Geradas {i + 1} rodadas...")
        print(f"✅ Geradas {total} rodadas de teste")
    
    print("="*80)
    print(f"✅ TOTAL: {total} rodadas")
    print("="*80)
    return total

# =============================================================================
# ATUALIZAR DADOS
# =============================================================================

def atualizar_dados_leves():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        
        if USE_SQLITE:
            cur.execute('SELECT COUNT(*) FROM rodadas')
        else:
            cur.execute('SELECT COUNT(*) FROM rodadas')
        total = cur.fetchone()[0]
        cache['leves']['total_rodadas'] = total
        
        if USE_SQLITE:
            cur.execute('SELECT player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 50')
        else:
            cur.execute('SELECT player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 50')
        rows = cur.fetchall()
        cache['leves']['ultimas_50'] = [{'player_score': r[0], 'banker_score': r[1], 'resultado': r[2]} for r in rows]
        
        if USE_SQLITE:
            cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 20')
        else:
            cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 20')
        rows = cur.fetchall()
        ultimas = []
        for row in rows:
            if USE_SQLITE:
                data_hora = datetime.fromisoformat(row[0])
            else:
                data_hora = row[0]
            brasilia = data_hora.astimezone(timezone(timedelta(hours=-3)))
            cor = '🔴' if row[3] == 'BANKER' else '🔵' if row[3] == 'PLAYER' else '🟡'
            ultimas.append({
                'hora': brasilia.strftime('%H:%M:%S'),
                'resultado': row[3],
                'cor': cor,
                'player': row[1],
                'banker': row[2]
            })
        cache['leves']['ultimas_20'] = ultimas
        cache['leves']['ultima_atualizacao'] = datetime.now(timezone.utc)
        
        cur.close()
        print(f"📊 Atualizado: {total} rodadas", end='\r')
    except Exception as e:
        print(f"⚠️ Erro: {e}")

def atualizar_dados_pesados():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        agora = datetime.now(timezone.utc)
        periodos = {
            '10min': agora - timedelta(minutes=10),
            '1h': agora - timedelta(hours=1),
            '6h': agora - timedelta(hours=6),
            '12h': agora - timedelta(hours=12),
            '24h': agora - timedelta(hours=24),
            '48h': agora - timedelta(hours=48),
            '72h': agora - timedelta(hours=72)
        }
        for nome, limite in periodos.items():
            if USE_SQLITE:
                cur.execute('SELECT COUNT(*) FROM rodadas WHERE data_hora >= ?', (limite,))
            else:
                cur.execute('SELECT COUNT(*) FROM rodadas WHERE data_hora >= %s', (limite,))
            cache['pesados']['periodos'][nome] = cur.fetchone()[0]
        cur.close()
        cache['pesados']['ultima_atualizacao'] = datetime.now(timezone.utc)
    except Exception as e:
        print(f"⚠️ Erro periodos: {e}")

# =============================================================================
# LOOP PESADO
# =============================================================================

def loop_pesado():
    print("🔄 Loop pesado iniciado")
    while True:
        time.sleep(0.1)
        try:
            atualizar_dados_pesados()
        except Exception as e:
            print(f"❌ Erro loop: {e}")

# =============================================================================
# COLETA DE DADOS
# =============================================================================

LATEST_API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo/latest"
API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Cache-Control': 'no-cache'
}
INTERVALO_LATEST = 0.3

ultimo_id_latest = None

def buscar_latest():
    global ultimo_id_latest
    try:
        response = requests.get(LATEST_API_URL, headers=HEADERS, timeout=2)
        if response.status_code == 200:
            dados = response.json()
            novo_id = dados.get('id')
            if novo_id and novo_id != ultimo_id_latest:
                ultimo_id_latest = novo_id
                data = dados.get('data', {})
                result = data.get('result', {})
                
                player_dice = result.get('playerDice', {})
                banker_dice = result.get('bankerDice', {})
                player_score = player_dice.get('first', 0) + player_dice.get('second', 0)
                banker_score = banker_dice.get('first', 0) + banker_dice.get('second', 0)
                
                outcome = result.get('outcome', '')
                if outcome == 'PlayerWon':
                    resultado = 'PLAYER'
                elif outcome == 'BankerWon':
                    resultado = 'BANKER'
                else:
                    resultado = 'TIE'
                
                rodada = {
                    'id': novo_id,
                    'data_hora': datetime.now(timezone.utc),
                    'player_score': player_score,
                    'banker_score': banker_score,
                    'resultado': resultado
                }
                print(f"📡 LATEST: {player_score} vs {banker_score} - {resultado}")
                return rodada
        return None
    except Exception as e:
        return None

def loop_latest():
    print("📡 Coletor LATEST iniciado")
    while True:
        try:
            rodada = buscar_latest()
            if rodada:
                fila_rodadas.append(rodada)
            time.sleep(INTERVALO_LATEST)
        except Exception as e:
            time.sleep(1)

# =============================================================================
# CACHE
# =============================================================================
cache = {
    'leves': {
        'ultimas_50': [],
        'ultimas_20': [],
        'total_rodadas': 0,
        'ultima_atualizacao': None,
        'previsao': None
    },
    'pesados': {
        'periodos': {},
        'ultima_atualizacao': None
    },
    'estatisticas': {
        'total_previsoes': 0,
        'acertos': 0,
        'erros': 0,
        'ultimas_20_previsoes': [],
    },
    'ensemble': None,
    'mapa_mental': None,
    'indicadores': None,
    'ultima_previsao': None,
    'ultimo_resultado_real': None
}

fila_rodadas = deque(maxlen=500)

# =============================================================================
# PROCESSADOR DE FILA
# =============================================================================

def processar_fila():
    print("🚀 Processador iniciado")
    
    historico_buffer = []
    ultima_previsao_feita = None
    
    while True:
        try:
            if fila_rodadas:
                batch = list(fila_rodadas)
                fila_rodadas.clear()
                
                for rodada in batch:
                    if salvar_rodada(rodada, 'principal'):
                        historico_buffer.append(rodada)
                        print(f"✅ SALVO: {rodada['player_score']} vs {rodada['banker_score']} - {rodada['resultado']} | Buffer: {len(historico_buffer)}")
                        
                        if ultima_previsao_feita:
                            resultado_real = rodada['resultado']
                            if resultado_real != 'TIE':
                                acertou = (ultima_previsao_feita['previsao'] == resultado_real)
                                
                                cache['estatisticas']['total_previsoes'] += 1
                                if acertou:
                                    cache['estatisticas']['acertos'] += 1
                                else:
                                    cache['estatisticas']['erros'] += 1
                                
                                cache['estatisticas']['ultimas_20_previsoes'].insert(0, {
                                    'data': datetime.now().strftime('%d/%m %H:%M:%S'),
                                    'previsao': ultima_previsao_feita['previsao'],
                                    'simbolo': ultima_previsao_feita['simbolo'],
                                    'confianca': ultima_previsao_feita['confianca'],
                                    'resultado_real': resultado_real,
                                    'acertou': acertou,
                                    'estrategias': ultima_previsao_feita.get('estrategias', []),
                                    'modo': ultima_previsao_feita.get('modo', 'ENSEMBLE'),
                                    'total_agentes': ultima_previsao_feita.get('total_agentes', 0),
                                    'geracao': ultima_previsao_feita.get('geracao', 0)
                                })
                                
                                while len(cache['estatisticas']['ultimas_20_previsoes']) > 20:
                                    cache['estatisticas']['ultimas_20_previsoes'].pop()
                                
                                print(f"📈 Precisão: {cache['estatisticas']['acertos']}/{cache['estatisticas']['total_previsoes']}")
                            
                            ultima_previsao_feita = None
                        
                        if len(historico_buffer) >= 30 and ML_AVAILABLE and cache.get('ensemble') and ultima_previsao_feita is None:
                            historico_completo = []
                            for r in historico_buffer[-50:]:
                                historico_completo.append({
                                    'player_score': r['player_score'],
                                    'banker_score': r['banker_score'],
                                    'resultado': r['resultado']
                                })
                            
                            try:
                                previsao = cache['ensemble'].prever(historico_completo)
                                if previsao['previsao'] != 'AGUARDANDO':
                                    ultima_previsao_feita = {
                                        'modo': previsao['modo'],
                                        'previsao': previsao['previsao'],
                                        'simbolo': previsao['simbolo'],
                                        'confianca': previsao['confianca'],
                                        'estrategias': previsao.get('estrategias', []),
                                        'total_agentes': previsao.get('total_agentes', 0),
                                        'geracao': previsao.get('geracao', 0)
                                    }
                                    cache['leves']['previsao'] = ultima_previsao_feita
                                    print(f"   ✅ PREVISÃO: {ultima_previsao_feita['previsao']} com {ultima_previsao_feita['confianca']}%")
                            except Exception as e:
                                print(f"⚠️ Erro previsão: {e}")
                    
                    atualizar_dados_leves()
            
            time.sleep(0.1)
            
        except Exception as e:
            print(f"❌ Erro processador: {e}")
            traceback.print_exc()
            time.sleep(0.5)

# =============================================================================
# ROTAS API
# =============================================================================

def calcular_precisao():
    total = cache['estatisticas']['total_previsoes']
    if total == 0:
        return 0
    return round((cache['estatisticas']['acertos'] / total) * 100)

@app.route('/api/stats')
def api_stats():
    stats_ensemble = cache['ensemble'].get_stats() if cache.get('ensemble') else {}
    
    especialistas_formatados = []
    if stats_ensemble.get('especialistas'):
        for esp in stats_ensemble['especialistas']:
            especialistas_formatados.append({
                'nome': esp['nome'],
                'acertos': esp['acertos'],
                'erros': esp['erros'],
                'precisao': esp['precisao'],
                'peso': esp['peso'],
                'saude': 100,
                'fitness': esp['precisao'],
                'especialidade': esp.get('padrao', esp.get('especialidade', '-')),
                'geracao': esp.get('geracao', 0)
            })
    
    return jsonify({
        'ultima_atualizacao': cache['leves']['ultima_atualizacao'].strftime('%d/%m %H:%M:%S') if cache['leves']['ultima_atualizacao'] else None,
        'total_rodadas': cache['leves']['total_rodadas'],
        'ultimas_20': cache['leves']['ultimas_20'],
        'previsao': cache['leves']['previsao'],
        'periodos': cache['pesados']['periodos'],
        'estatisticas': {
            'total_previsoes': cache['estatisticas']['total_previsoes'],
            'acertos': cache['estatisticas']['acertos'],
            'erros': cache['estatisticas']['erros'],
            'precisao': calcular_precisao(),
            'ultimas_20_previsoes': cache['estatisticas']['ultimas_20_previsoes'],
            'estrategias': especialistas_formatados
        },
        'aprendizado': stats_ensemble,
        'total_agentes': stats_ensemble.get('total_agentes', 0),
        'geracao': stats_ensemble.get('evolucao', {}).get('geracao_atual', 0)
    })

@app.route('/api/tabela/<int:limite>')
def api_tabela(limite):
    limite = min(max(limite, 50), 2000)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cur = conn.cursor()
        if USE_SQLITE:
            cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT ?', (limite,))
        else:
            cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT %s', (limite,))
        rows = cur.fetchall()
        cur.close()
        
        resultado = []
        for row in rows:
            if USE_SQLITE:
                data_hora = datetime.fromisoformat(row[0])
            else:
                data_hora = row[0]
            brasilia = data_hora.astimezone(timezone(timedelta(hours=-3)))
            resultado.append({
                'data': brasilia.strftime('%d/%m %H:%M:%S'),
                'player': row[1],
                'banker': row[2],
                'resultado': row[3],
                'cor': '🔴' if row[3] == 'BANKER' else '🔵' if row[3] == 'PLAYER' else '🟡'
            })
        
        return jsonify(resultado)
        
    except Exception as e:
        print(f"❌ Erro tabela: {e}")
        return jsonify([])

@app.route('/api/aprendizado')
def api_aprendizado():
    if ML_AVAILABLE and cache.get('ensemble'):
        return jsonify(cache['ensemble'].get_stats())
    return jsonify({'status': 'inativo'})

# =============================================================================
# INICIALIZAÇÃO
# =============================================================================

def inicializar_sistema():
    print("\n" + "="*80)
    print("🚀 INICIALIZANDO SISTEMA")
    print("="*80)
    
    if ML_AVAILABLE:
        try:
            cache['indicadores'] = BacBoIndicators()
            cache['mapa_mental'] = MapaMental()
            cache['ensemble'] = EnsembleEvolutivo()
            stats = cache['ensemble'].get_stats()
            print(f"✅ Ensemble: {stats['total_agentes']} especialistas")
        except Exception as e:
            print(f"⚠️ Erro ensemble: {e}")
            cache['ensemble'] = None
    else:
        print("⚠️ ML não disponível")
    
    print("="*80)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("="*80)
    print("🚀 BACBO PREDICTOR - VERSÃO ESTÁVEL")
    print("="*80)
    
    # Criar diretórios
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    
    # Inicializar banco
    init_db()
    
    # Carregar rodadas
    total_passadas = carregar_rodadas_passadas()
    
    # Atualizar dados
    atualizar_dados_leves()
    atualizar_dados_pesados()
    
    print(f"\n📊 TOTAL: {cache['leves']['total_rodadas']} rodadas no banco")
    
    # Inicializar sistema
    inicializar_sistema()
    
    # Iniciar threads
    threading.Thread(target=loop_latest, daemon=True).start()
    threading.Thread(target=processar_fila, daemon=True).start()
    threading.Thread(target=loop_pesado, daemon=True).start()
    
    def loop_atualizacao_leves():
        while True:
            time.sleep(30)
            atualizar_dados_leves()
    threading.Thread(target=loop_atualizacao_leves, daemon=True).start()
    
    PORT = int(os.environ.get("PORT", 5000))
    print("\n" + "="*80)
    print(f"🚀 FLASK NA PORTA {PORT}")
    print(f"🎯 http://localhost:{PORT}")
    print("="*80)
    
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
