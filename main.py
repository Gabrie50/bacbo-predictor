# main.py - VERSÃO COMPLETA COM CARGA DE DADOS HISTÓRICOS
# =============================================================================

import os
import time
import requests
import json
import urllib.parse
import threading
import random
from datetime import datetime, timedelta, timezone
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS
import pg8000
import ssl
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
        'mensagem': 'Ensemble Evolutivo Online',
        'timestamp': time.time(),
        'versao': '10.0 - Evolutivo',
        'total_agentes': cache.get('ensemble').get_stats()['total_agentes'] if cache.get('ensemble') else 0
    })

@app.route('/', methods=['GET'])
def home_rapida():
    return render_template('index.html')

@app.route('/mapa-mental')
def mapa_mental():
    return render_template('mapa_mental.html')

# =============================================================================
# 🧠 IMPORTAR ENSEMBLE EVOLUTIVO
# =============================================================================
from app.ml.ensemble import EnsembleEvolutivo
from app.ml.memory_map import MapaMental
from app.ml.indicators import BacBoIndicators

# =============================================================================
# CONFIGURAÇÕES
# =============================================================================
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_uHONl9tJ1gDF@ep-patient-rice-amoqsdum-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require")

parsed = urllib.parse.urlparse(DATABASE_URL)
DB_USER = parsed.username
DB_PASSWORD = parsed.password
DB_HOST = parsed.hostname
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path[1:]

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

# Configurações das fontes
LATEST_API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo/latest"
API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
    'Origin': 'https://www.casino.org',
    'Referer': 'https://www.casino.org/',
    'Cache-Control': 'no-cache'
}

INTERVALO_LATEST = 1
PORT = int(os.environ.get("PORT", 5000))

# =============================================================================
# CACHE GLOBAL
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

# Fila de rodadas
fila_rodadas = deque(maxlen=500)
ultimo_id_latest = None
ultimo_id_api = None

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def calcular_precisao():
    total = cache['estatisticas']['total_previsoes']
    if total == 0:
        return 0
    return round((cache['estatisticas']['acertos'] / total) * 100)

def get_db_connection():
    try:
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
        print(f"❌ Erro ao conectar: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível")
        return False
    try:
        cur = conn.cursor()
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
                contexto_json JSONB,
                total_agentes INTEGER,
                geracao INTEGER
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tabelas criadas/verificadas")
        return True
    except Exception as e:
        print(f"❌ Erro ao criar tabelas: {e}")
        return False

def salvar_rodada(rodada, fonte):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
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
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao salvar: {e}")
        return False

def salvar_previsao(previsao, resultado_real, acertou, contexto, total_agentes, geracao):
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        
        estrategias_str = ','.join(previsao.get('estrategias', []))[:500]
        
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
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️ Erro ao salvar previsão: {e}")
        return False

# =============================================================================
# CARGA DE DADOS HISTÓRICOS
# =============================================================================

def carregar_historico_api():
    """Carrega dados históricos da API"""
    print("\n📚 CARREGANDO DADOS HISTÓRICOS DA API...")
    
    total_carregadas = 0
    pagina = 0
    
    while pagina < 10:  # Carrega até 10 páginas (1000 rodadas)
        try:
            params = {
                'page': pagina,
                'size': 100,
                'sort': 'data.settledAt,desc',
                '_t': int(time.time() * 1000)
            }
            
            response = requests.get(API_URL, params=params, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                dados = response.json()
                
                if not dados or len(dados) == 0:
                    break
                
                novas = 0
                for item in dados:
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
                            novas += 1
                            total_carregadas += 1
                            
                    except Exception as e:
                        continue
                
                print(f"   Página {pagina}: +{novas} rodadas")
                
                if novas == 0:
                    break
                    
                pagina += 1
                time.sleep(0.5)
                
            else:
                print(f"   ⚠️ Página {pagina} retornou status {response.status_code}")
                break
                
        except Exception as e:
            print(f"   ⚠️ Erro na página {pagina}: {e}")
            break
    
    print(f"✅ Total carregado: {total_carregadas} rodadas")
    return total_carregadas

# =============================================================================
# COLETA DE DADOS EM TEMPO REAL
# =============================================================================

def buscar_latest():
    global ultimo_id_latest
    try:
        response = requests.get(LATEST_API_URL, headers=HEADERS, timeout=3)
        
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
                print(f"📡 NOVA RODADA: {player_score} vs {banker_score} - {resultado}")
                return rodada
        return None
    except Exception as e:
        print(f"⚠️ Erro LATEST: {e}")
        return None

def loop_latest():
    print("📡 Coletor LATEST iniciado...")
    while True:
        try:
            rodada = buscar_latest()
            if rodada:
                fila_rodadas.append(rodada)
            time.sleep(INTERVALO_LATEST)
        except Exception as e:
            print(f"❌ Erro no coletor: {e}")
            time.sleep(2)

# =============================================================================
# ATUALIZAR DADOS DO BANCO
# =============================================================================

def atualizar_dados_leves():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute('SELECT player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 50')
        rows = cur.fetchall()
        cache['leves']['ultimas_50'] = [{'player_score': r[0], 'banker_score': r[1], 'resultado': r[2]} for r in rows]
        
        cur.execute('SELECT COUNT(*) FROM rodadas')
        cache['leves']['total_rodadas'] = cur.fetchone()[0]
        
        # Últimas 20 para o frontend
        cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 20')
        rows = cur.fetchall()
        ultimas = []
        for row in rows:
            brasilia = row[0].astimezone(timezone(timedelta(hours=-3)))
            cor = '🔴' if row[3] == 'BANKER' else '🔵' if row[3] == 'PLAYER' else '🟡'
            ultimas.append({
                'hora': brasilia.strftime('%H:%M:%S'),
                'resultado': row[3],
                'cor': cor,
                'player': row[1],
                'banker': row[2]
            })
        cache['leves']['ultimas_20'] = ultimas
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro atualizar dados: {e}")

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
            cur.execute('SELECT COUNT(*) FROM rodadas WHERE data_hora >= %s', (limite,))
            cache['pesados']['periodos'][nome] = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as e:
        print(f"⚠️ Erro periodos: {e}")

# =============================================================================
# PROCESSADOR DE FILA
# =============================================================================

def processar_fila():
    print("🚀 Processador ENSEMBLE EVOLUTIVO iniciado...")
    
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
                        cache['ultimo_resultado_real'] = rodada['resultado']
                        print(f"✅ SALVO: {rodada['player_score']} vs {rodada['banker_score']} - {rodada['resultado']} | Total: {len(historico_buffer)}")
                        
                        # =====================================================
                        # VERIFICAR PREVISÃO ANTERIOR
                        # =====================================================
                        if ultima_previsao_feita:
                            resultado_real = rodada['resultado']
                            if resultado_real != 'TIE':
                                acertou = (ultima_previsao_feita['previsao'] == resultado_real)
                                
                                print(f"\n📊 VERIFICANDO PREVISÃO:")
                                print(f"   Previsão: {ultima_previsao_feita['previsao']} | Real: {resultado_real} | {'✅' if acertou else '❌'}")
                                
                                salvar_previsao(
                                    ultima_previsao_feita, 
                                    resultado_real, 
                                    acertou, 
                                    historico_buffer[-50:],
                                    ultima_previsao_feita.get('total_agentes', 0),
                                    ultima_previsao_feita.get('geracao', 0)
                                )
                                
                                cache['estatisticas']['total_previsoes'] += 1
                                if acertou:
                                    cache['estatisticas']['acertos'] += 1
                                else:
                                    cache['estatisticas']['erros'] += 1
                                
                                if cache.get('ensemble'):
                                    cache['ensemble'].aprender(resultado_real)
                                
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
                                
                                if len(cache['estatisticas']['ultimas_20_previsoes']) > 20:
                                    cache['estatisticas']['ultimas_20_previsoes'].pop()
                                
                                print(f"📈 Precisão: {calcular_precisao()}%")
                            
                            ultima_previsao_feita = None
                        
                        # =====================================================
                        # FAZER NOVA PREVISÃO
                        # =====================================================
                        if len(historico_buffer) >= 30 and cache.get('ensemble') and ultima_previsao_feita is None:
                            print(f"\n🔮 FAZENDO PREVISÃO...")
                            
                            historico_completo = []
                            for r in historico_buffer[-50:]:
                                historico_completo.append({
                                    'player_score': r['player_score'],
                                    'banker_score': r['banker_score'],
                                    'resultado': r['resultado']
                                })
                            
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
                    
                    cache['leves']['ultima_atualizacao'] = datetime.now(timezone.utc)
                    atualizar_dados_leves()
            
            time.sleep(0.1)
            
        except Exception as e:
            print(f"❌ Erro no processador: {e}")
            traceback.print_exc()
            time.sleep(0.5)

# =============================================================================
# ROTAS DA API
# =============================================================================

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
    limite = min(max(limite, 50), 1000)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cur = conn.cursor()
    cur.execute('SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT %s', (limite,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    resultado = []
    for row in rows:
        brasilia = row[0].astimezone(timezone(timedelta(hours=-3)))
        resultado.append({
            'data': brasilia.strftime('%d/%m %H:%M:%S'),
            'player': row[1],
            'banker': row[2],
            'resultado': row[3],
            'cor': '🔴' if row[3] == 'BANKER' else '🔵' if row[3] == 'PLAYER' else '🟡'
        })
    return jsonify(resultado)

@app.route('/api/aprendizado')
def api_aprendizado():
    if cache.get('ensemble'):
        return jsonify(cache['ensemble'].get_stats())
    return jsonify({'erro': 'Ensemble não inicializado'})

# =============================================================================
# INICIALIZAÇÃO
# =============================================================================

def inicializar_sistema():
    print("\n" + "="*80)
    print("🚀 INICIALIZANDO BACBO - ENSEMBLE EVOLUTIVO")
    print("="*80)
    
    cache['indicadores'] = BacBoIndicators()
    cache['mapa_mental'] = MapaMental()
    cache['ensemble'] = EnsembleEvolutivo()
    
    stats = cache['ensemble'].get_stats()
    
    print("\n✅ Sistema inicializado com sucesso!")
    print(f"   🧠 {stats['total_agentes']} especialistas")
    print(f"   🗺️ Mapa mental: {stats['mapa_mental']['total']} memórias")
    print("="*80)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    print("="*80)
    print("🚀 BACBO PREDICTOR - ENSEMBLE EVOLUTIVO v10.0")
    print("="*80)
    
    # Inicializar banco
    init_db()
    
    # Carregar dados históricos
    print("\n📥 CARREGANDO DADOS HISTÓRICOS...")
    carregar_historico_api()
    
    # Atualizar dados
    atualizar_dados_leves()
    atualizar_dados_pesados()
    
    print(f"\n📊 TOTAL NO BANCO: {cache['leves']['total_rodadas']} rodadas")
    
    # Inicializar sistema
    inicializar_sistema()
    
    # Iniciar threads
    threading.Thread(target=loop_latest, daemon=True).start()
    threading.Thread(target=processar_fila, daemon=True).start()
    
    # Thread para atualizar dados periódicos
    def loop_atualizacao():
        while True:
            time.sleep(30)
            atualizar_dados_leves()
            atualizar_dados_pesados()
    threading.Thread(target=loop_atualizacao, daemon=True).start()
    
    print("\n" + "="*80)
    print("🚀 FLASK INICIANDO...")
    print(f"🎯 Acesse: http://localhost:{PORT}")
    print("="*80)
    
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
