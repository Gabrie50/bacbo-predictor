# main.py - VERSÃO CORRIGIDA COM HEADERS MELHORADOS E FALLBACK
# =============================================================================

import os
import time
import requests
import json
import urllib.parse
import threading
import websocket
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
        'total_agentes': cache.get('ensemble').get_stats()['total_agentes'] if cache.get('ensemble') else 0,
        'total_rodadas': cache['leves']['total_rodadas']
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

# =============================================================================
# CONFIGURAÇÕES DAS 3 FONTES
# =============================================================================
LATEST_API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo/latest"
WS_URL = "wss://api-cs.casino.org/svc-evolution-game-events/ws/bacbo"
API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo"

# HEADERS COMPLETOS (como um navegador real)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Origin': 'https://www.casino.org',
    'Referer': 'https://www.casino.org/',
    'Connection': 'keep-alive',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache'
}

TIMEOUT_API = 5
MAX_RETRIES = 3
RETRY_DELAY = 1
INTERVALO_LATEST = 0.2
INTERVALO_WS_FALLBACK = 3
INTERVALO_NORMAL_FALLBACK = 10
PORT = int(os.environ.get("PORT", 5000))

# =============================================================================
# CONTROLE DE FALHAS
# =============================================================================
falhas_latest = 0
falhas_websocket = 0
falhas_api_normal = 0
LIMITE_FALHAS = 10  # Aumentado para dar mais chances

fontes_status = {
    'latest': {'status': 'ativo', 'total': 0, 'falhas': 0, 'prioridade': 1},
    'websocket': {'status': 'standby', 'total': 0, 'falhas': 0, 'prioridade': 2},
    'api_normal': {'status': 'standby', 'total': 0, 'falhas': 0, 'prioridade': 3}
}

fonte_ativa = 'latest'

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
ultimo_id_websocket = None
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

def salvar_previsao(previsao, resultado_real, acertou, total_agentes, geracao):
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
# GERAR RODADAS DE TESTE (FALLBACK QUANDO API ESTIVER MORTA)
# =============================================================================

def gerar_rodada_teste():
    """Gera uma rodada de teste quando a API não responde"""
    global ultimo_id_latest
    
    # Gerar ID único
    novo_id = f"teste_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
    
    # Gerar scores aleatórios
    player_score = random.randint(2, 12)
    banker_score = random.randint(2, 12)
    
    # Decidir resultado baseado nos scores
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
    
    print(f"🧪 [TESTE] Rodada gerada: {player_score} vs {banker_score} - {resultado}")
    return rodada

# =============================================================================
# CARGA HISTÓRICA DE RODADAS PASSADAS
# =============================================================================

def carregar_rodadas_passadas():
    """Carrega rodadas passadas da API normal ou gera dados de teste"""
    print("\n" + "="*80)
    print("📥 CARREGANDO RODADAS PASSADAS")
    print("="*80)
    
    total_carregadas = 0
    pagina = 0
    max_paginas = 3
    
    # Tentar API real primeiro
    api_funcionou = False
    
    while pagina < max_paginas and not api_funcionou:
        try:
            params = {
                'page': pagina,
                'size': 50,
                'sort': 'data.settledAt,desc',
                '_t': int(time.time() * 1000)
            }
            
            print(f"📡 Tentando API página {pagina}...", end=' ')
            response = requests.get(API_URL, params=params, headers=HEADERS, timeout=10)
            
            if response.status_code == 200:
                dados = response.json()
                if dados and len(dados) > 0:
                    api_funcionou = True
                    print(f"✅ API funcionou!")
                    
                    for item in dados[:50]:
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
                                total_carregadas += 1
                                
                        except Exception as e:
                            continue
                    
                    break
                else:
                    print("⚠️ Sem dados")
            else:
                print(f"❌ Status {response.status_code}")
                
            pagina += 1
            time.sleep(0.5)
            
        except Exception as e:
            print(f"❌ Erro: {e}")
            pagina += 1
    
    # Se API falhou, gerar dados de teste
    if total_carregadas == 0:
        print("\n⚠️ API não respondeu. Gerando dados de teste...")
        for i in range(100):
            rodada = gerar_rodada_teste()
            if salvar_rodada(rodada, 'teste'):
                total_carregadas += 1
        print(f"✅ Geradas {total_carregadas} rodadas de teste")
    
    print("="*80)
    print(f"✅ TOTAL CARREGADO: {total_carregadas} rodadas")
    print("="*80)
    return total_carregadas

# =============================================================================
# 🔄 FUNÇÃO PARA ALTERNAR FONTE ATIVA
# =============================================================================
def alternar_fonte():
    global fonte_ativa, falhas_latest, falhas_websocket, falhas_api_normal

    if fonte_ativa == 'latest' and falhas_latest >= LIMITE_FALHAS:
        print(f"\n⚠️ LATEST falhou {falhas_latest} vezes - Alternando para WEBSOCKET")
        fonte_ativa = 'websocket'
        fontes_status['latest']['status'] = 'falha'
        fontes_status['websocket']['status'] = 'ativo'

    elif fonte_ativa == 'websocket' and falhas_websocket >= LIMITE_FALHAS:
        print(f"\n⚠️ WEBSOCKET falhou {falhas_websocket} vezes - Alternando para API NORMAL")
        fonte_ativa = 'api_normal'
        fontes_status['websocket']['status'] = 'falha'
        fontes_status['api_normal']['status'] = 'ativo'

    elif fonte_ativa == 'api_normal' and falhas_api_normal >= LIMITE_FALHAS:
        print(f"\n⚠️ Todas as fontes falharam - Usando gerador de teste")
        falhas_latest = 0
        falhas_websocket = 0
        falhas_api_normal = 0
        fonte_ativa = 'teste'
        fontes_status['latest']['status'] = 'teste'
        fontes_status['websocket']['status'] = 'teste'
        fontes_status['api_normal']['status'] = 'teste'

# =============================================================================
# 📡 FONTE 1: API LATEST (INTERVALO 0.2s)
# =============================================================================

def buscar_latest():
    global ultimo_id_latest, falhas_latest, fonte_ativa

    try:
        response = requests.get(LATEST_API_URL, headers=HEADERS, timeout=3)

        if response.status_code == 200:
            dados = response.json()
            novo_id = dados.get('id')
            data = dados.get('data', {})
            result = data.get('result', {})

            if novo_id and novo_id != ultimo_id_latest:
                if fonte_ativa == 'latest':
                    falhas_latest = 0

                ultimo_id_latest = novo_id

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

                fontes_status['latest']['total'] += 1
                print(f"\n📡 [PRINCIPAL] LATEST: {player_score} vs {banker_score} - {resultado}")
                return rodada
            else:
                return None
        else:
            if fonte_ativa == 'latest':
                falhas_latest += 1
                fontes_status['latest']['falhas'] += 1
                print(f"⚠️ LATEST falha {falhas_latest}/{LIMITE_FALHAS} (Status: {response.status_code})")
                if falhas_latest >= LIMITE_FALHAS:
                    alternar_fonte()
            return None

    except Exception as e:
        if fonte_ativa == 'latest':
            falhas_latest += 1
            fontes_status['latest']['falhas'] += 1
            print(f"⚠️ LATEST erro: {e} - falha {falhas_latest}/{LIMITE_FALHAS}")
            if falhas_latest >= LIMITE_FALHAS:
                alternar_fonte()
        return None

# =============================================================================
# 📡 FONTE 2: WEBSOCKET
# =============================================================================

def on_ws_message(ws, message):
    global ultimo_id_websocket, falhas_websocket, fonte_ativa

    try:
        data = json.loads(message)

        if 'data' in data and 'result' in data['data']:
            game_data = data['data']
            result = game_data['result']
            novo_id = game_data.get('id')

            if novo_id and novo_id != ultimo_id_websocket:
                if fonte_ativa == 'websocket':
                    falhas_websocket = 0

                ultimo_id_websocket = novo_id

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

                fontes_status['websocket']['total'] += 1

                if fonte_ativa == 'websocket':
                    fila_rodadas.append(rodada)
                    print(f"\n⚡ [BACKUP] WEBSOCKET: {player_score} vs {banker_score} - {resultado}")

    except Exception as e:
        print(f"⚠️ Erro WS: {e}")

def on_ws_error(ws, error):
    global falhas_websocket, fonte_ativa
    if fonte_ativa == 'websocket':
        falhas_websocket += 1
        fontes_status['websocket']['falhas'] += 1
        print(f"🔌 WS Erro: {error} - falha {falhas_websocket}/{LIMITE_FALHAS}")
        if falhas_websocket >= LIMITE_FALHAS:
            alternar_fonte()

def on_ws_close(ws, close_status_code, close_msg):
    global falhas_websocket, fonte_ativa
    if fonte_ativa == 'websocket':
        falhas_websocket += 1
        fontes_status['websocket']['falhas'] += 1
        print(f"🔌 WS Fechado - falha {falhas_websocket}/{LIMITE_FALHAS}")
        if falhas_websocket >= LIMITE_FALHAS:
            alternar_fonte()
    time.sleep(5)
    iniciar_websocket()

def on_ws_open(ws):
    global falhas_websocket, fonte_ativa
    print("✅ WEBSOCKET CONECTADO! (modo backup)")
    if fonte_ativa == 'websocket':
        falhas_websocket = 0

def iniciar_websocket():
    def run():
        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=on_ws_open,
            on_message=on_ws_message,
            on_error=on_ws_error,
            on_close=on_ws_close
        )
        ws.run_forever()

    threading.Thread(target=run, daemon=True).start()

# =============================================================================
# 📡 FONTE 3: API NORMAL (FALLBACK)
# =============================================================================

def buscar_api_normal():
    global ultimo_id_api, falhas_api_normal, fonte_ativa

    try:
        params = {
            'page': 0,
            'size': 20,
            'sort': 'data.settledAt,desc',
            '_t': int(time.time() * 1000)
        }

        response = requests.get(API_URL, params=params, headers=HEADERS, timeout=TIMEOUT_API)
        
        if response.status_code == 200:
            dados = response.json()
            if dados and len(dados) > 0:
                if fonte_ativa == 'api_normal':
                    falhas_api_normal = 0

                rodadas = []
                for item in dados[:10]:
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
                        rodadas.append(rodada)
                    except:
                        continue

                fontes_status['api_normal']['total'] += len(rodadas)

                if fonte_ativa == 'api_normal':
                    print(f"\n📚 [FALLBACK] API NORMAL: {len(rodadas)} rodadas")
                    return rodadas

        return None

    except Exception as e:
        if fonte_ativa == 'api_normal':
            falhas_api_normal += 1
            fontes_status['api_normal']['falhas'] += 1
            print(f"⚠️ API Normal erro - falha {falhas_api_normal}/{LIMITE_FALHAS}")
            if falhas_api_normal >= LIMITE_FALHAS:
                alternar_fonte()
        return None

# =============================================================================
# 📡 FONTE 4: GERADOR DE TESTE (QUANDO TUDO FALHA)
# =============================================================================

def buscar_teste():
    global fonte_ativa
    if fonte_ativa == 'teste':
        rodada = gerar_rodada_teste()
        return rodada
    return None

# =============================================================================
# LOOPS DE COLETA
# =============================================================================

def loop_latest():
    print("📡 [PRINCIPAL] Coletor LATEST iniciado (0.2s)...")
    while True:
        try:
            rodada = None
            if fonte_ativa == 'latest':
                rodada = buscar_latest()
            elif fonte_ativa == 'teste':
                rodada = buscar_teste()
                time.sleep(1)  # Delay maior para teste
            
            if rodada:
                fila_rodadas.append(rodada)
            time.sleep(INTERVALO_LATEST)
        except Exception as e:
            print(f"❌ Erro no loop LATEST: {e}")
            time.sleep(INTERVALO_LATEST)

def loop_websocket_fallback():
    print("⚡ [BACKUP] Monitor WebSocket iniciado...")
    while True:
        try:
            time.sleep(1)
        except Exception as e:
            print(f"❌ Erro no monitor WS: {e}")
            time.sleep(1)

def loop_api_fallback():
    print("📚 [FALLBACK] Coletor API NORMAL iniciado (10s)...")
    while True:
        try:
            if fonte_ativa == 'api_normal':
                rodadas = buscar_api_normal()
                if rodadas:
                    for rodada in rodadas:
                        fila_rodadas.append(rodada)
            time.sleep(INTERVALO_NORMAL_FALLBACK)
        except Exception as e:
            print(f"❌ Erro API Normal: {e}")
            time.sleep(INTERVALO_NORMAL_FALLBACK)

# =============================================================================
# ATUALIZAR DADOS
# =============================================================================

def atualizar_dados_leves():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        
        # Total de rodadas
        cur.execute('SELECT COUNT(*) FROM rodadas')
        total = cur.fetchone()[0]
        cache['leves']['total_rodadas'] = total
        print(f"📊 Atualizado: {total} rodadas no banco")
        
        # Últimas 50
        cur.execute('SELECT player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 50')
        rows = cur.fetchall()
        cache['leves']['ultimas_50'] = [{'player_score': r[0], 'banker_score': r[1], 'resultado': r[2]} for r in rows]
        
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
        cache['leves']['ultima_atualizacao'] = datetime.now(timezone.utc)
        
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
        cache['pesados']['ultima_atualizacao'] = datetime.now(timezone.utc)
    except Exception as e:
        print(f"⚠️ Erro periodos: {e}")

# =============================================================================
# LOOP PESADO
# =============================================================================

def loop_pesado():
    print("🔄 [PESADO] Loop de atualização iniciado...")
    while True:
        time.sleep(0.1)
        try:
            atualizar_dados_pesados()
        except Exception as e:
            print(f"❌ Erro loop pesado: {e}")

# =============================================================================
# PROCESSADOR DE FILA COM ENSEMBLE
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
                    if salvar_rodada(rodada, fonte_ativa):
                        historico_buffer.append(rodada)
                        cache['ultimo_resultado_real'] = rodada['resultado']
                        print(f"✅ SALVO: {rodada['player_score']} vs {rodada['banker_score']} - {rodada['resultado']} | Buffer: {len(historico_buffer)}")
                        
                        # =====================================================
                        # VERIFICAR PREVISÃO ANTERIOR
                        # =====================================================
                        if ultima_previsao_feita:
                            resultado_real = rodada['resultado']
                            if resultado_real != 'TIE':
                                acertou = (ultima_previsao_feita['previsao'] == resultado_real)
                                
                                print(f"\n📊 PREVISÃO ANTERIOR: {ultima_previsao_feita['previsao']} | Real: {resultado_real} | {'✅' if acertou else '❌'}")
                                
                                salvar_previsao(
                                    ultima_previsao_feita, 
                                    resultado_real, 
                                    acertou,
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
                                
                                while len(cache['estatisticas']['ultimas_20_previsoes']) > 20:
                                    cache['estatisticas']['ultimas_20_previsoes'].pop()
                                
                                print(f"📈 Precisão: {calcular_precisao()}%")
                            
                            ultima_previsao_feita = None
                        
                        # =====================================================
                        # FAZER NOVA PREVISÃO
                        # =====================================================
                        if len(historico_buffer) >= 30 and cache.get('ensemble') and ultima_previsao_feita is None:
                            print(f"\n🔮 FAZENDO PREVISÃO COM {len(historico_buffer)} rodadas...")
                            
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
                                print(f"   📊 Estratégias: {ultima_previsao_feita['estrategias'][:3]}")
                    
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
        'fonte_ativa': fonte_ativa,
        'fontes': fontes_status,
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
    limite = min(max(limite, 50), 3000)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
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
        
    except Exception as e:
        print(f"❌ Erro em api_tabela: {e}")
        return jsonify([])

@app.route('/api/aprendizado')
def api_aprendizado():
    if cache.get('ensemble'):
        return jsonify(cache['ensemble'].get_stats())
    return jsonify({'erro': 'Ensemble não inicializado'})

@app.route('/api/curto-prazo')
def api_curto_prazo():
    stats = cache['ensemble'].get_stats() if cache.get('ensemble') else {}
    return jsonify({
        'status': 'ativo',
        'estatisticas': {
            'precisao': stats.get('precisao', 0)
        }
    })

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
    print("   Começa com 7 especialistas e CRIA NOVOS conforme aprende!")
    print("="*80)
    
    # Inicializar banco
    init_db()
    
    # CARREGAR RODADAS PASSADAS (com fallback)
    total_passadas = carregar_rodadas_passadas()
    
    # Atualizar dados iniciais
    atualizar_dados_leves()
    atualizar_dados_pesados()
    
    print(f"\n📊 TOTAL DE RODADAS NO BANCO: {cache['leves']['total_rodadas']}")
    
    # Inicializar sistema
    inicializar_sistema()
    
    # Iniciar threads
    threading.Thread(target=loop_latest, daemon=True).start()
    threading.Thread(target=loop_websocket_fallback, daemon=True).start()
    threading.Thread(target=loop_api_fallback, daemon=True).start()
    threading.Thread(target=processar_fila, daemon=True).start()
    threading.Thread(target=loop_pesado, daemon=True).start()
    threading.Thread(target=iniciar_websocket, daemon=True).start()
    
    # Thread para atualizar dados periódicos
    def loop_atualizacao_leves():
        while True:
            time.sleep(30)
            atualizar_dados_leves()
    threading.Thread(target=loop_atualizacao_leves, daemon=True).start()
    
    print("\n" + "="*80)
    print("🚀 FLASK INICIANDO...")
    print("🎯 3 FONTES ATIVAS + GERADOR DE TESTE")
    print("🎯 LOOP PESADO ATIVO")
    print(f"🎯 Acesse: http://localhost:{PORT}")
    print("="*80)
    
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
