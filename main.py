"""BacBo Predictor - versão Ensemble de Agentes."""

import json
import os
import ssl
import threading
import time
import traceback
import urllib.parse
from collections import deque
from datetime import datetime, timedelta, timezone

import pg8000
import requests
from flask import Flask, jsonify
from flask_cors import CORS

from app.ml.ensemble import EnsembleAgentes
from app.ml.indicators import BacBoIndicators
from app.ml.memory_map import MapaMental

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/bacbo")
parsed = urllib.parse.urlparse(DATABASE_URL)
DB_USER = parsed.username or ""
DB_PASSWORD = parsed.password or ""
DB_HOST = parsed.hostname or "localhost"
DB_PORT = parsed.port or 5432
DB_NAME = parsed.path[1:] or "bacbo"

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

LATEST_API_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/bacbo/latest"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}
INTERVALO_LATEST = 0.3
PORT = int(os.environ.get("PORT", 5000))

cache = {
    "leves": {
        "ultimas_50": [],
        "ultimas_20": [],
        "total_rodadas": 0,
        "ultima_atualizacao": None,
        "previsao": None,
    },
    "pesados": {"periodos": {}, "ultima_atualizacao": None},
    "estatisticas": {
        "total_previsoes": 0,
        "acertos": 0,
        "erros": 0,
        "ultimas_20_previsoes": [],
    },
    "ensemble": None,
    "mapa_mental": None,
    "indicadores": None,
    "ultima_previsao": None,
    "ultimo_resultado_real": None,
}

fila_rodadas = deque(maxlen=500)
ultimo_id_latest = None


@app.route("/health", methods=["GET"])
def health_urgente():
    return jsonify(
        {
            "status": "ok",
            "mensagem": "Ensemble System Online",
            "timestamp": time.time(),
            "versao": "10.0 - Ensemble Agents",
        }
    )


@app.route("/", methods=["GET"])
def home_rapida():
    return jsonify(
        {
            "nome": "Bac Bo Predictor - Ensemble",
            "versao": "10.0 - Ensemble Agents",
            "status": "online",
            "health": "/health",
            "stats": "/api/stats",
        }
    )


def calcular_precisao() -> int:
    total = cache["estatisticas"]["total_previsoes"]
    if total == 0:
        return 0
    return round((cache["estatisticas"]["acertos"] / total) * 100)


def get_db_connection():
    try:
        conn = pg8000.connect(
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            ssl_context=SSL_CONTEXT,
            timeout=30,
        )
        conn.autocommit = False
        return conn
    except Exception as exc:
        print(f"❌ Erro ao conectar: {exc}")
        return None


def init_db() -> bool:
    conn = get_db_connection()
    if not conn:
        print("⚠️ Banco não disponível")
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
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
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_data_hora ON rodadas(data_hora DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_resultado ON rodadas(resultado)")
        cur.execute(
            """
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
                contexto_json JSONB
            )
            """
        )
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Tabelas criadas/verificadas")
        return True
    except Exception as exc:
        print(f"❌ Erro ao criar tabelas: {exc}")
        return False


def salvar_rodada(rodada: dict, fonte: str) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO rodadas
            (id, data_hora, player_score, banker_score, soma, resultado, fonte, dados_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                rodada["id"],
                rodada["data_hora"],
                rodada["player_score"],
                rodada["banker_score"],
                rodada["player_score"] + rodada["banker_score"],
                rodada["resultado"],
                fonte,
                json.dumps(rodada, default=str),
            ),
        )
        if cur.rowcount > 0:
            conn.commit()
            cur.close()
            conn.close()
            return True
        conn.rollback()
        cur.close()
        conn.close()
        return False
    except Exception as exc:
        print(f"❌ Erro ao salvar: {exc}")
        return False


def salvar_previsao(previsao: dict, resultado_real: str, acertou: bool, contexto: list) -> bool:
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cur = conn.cursor()
        estrategias_str = ",".join(previsao.get("estrategias", []))
        contexto_json = (
            json.dumps(
                [
                    {
                        "resultado": r["resultado"],
                        "player": r.get("player_score", 0),
                        "banker": r.get("banker_score", 0),
                    }
                    for r in contexto[:10]
                ]
            )
            if contexto
            else None
        )
        cur.execute(
            """
            INSERT INTO historico_previsoes
            (data_hora, previsao, simbolo, confianca, resultado_real, acertou,
             estrategias, modo, contexto_json)
            VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                previsao["previsao"],
                previsao.get("simbolo", "🔴" if previsao["previsao"] == "BANKER" else "🔵"),
                previsao["confianca"],
                resultado_real,
                acertou,
                estrategias_str,
                previsao.get("modo", "ENSEMBLE"),
                contexto_json,
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as exc:
        print(f"❌ Erro ao salvar previsão: {exc}")
        return False


def buscar_latest():
    global ultimo_id_latest
    try:
        response = requests.get(LATEST_API_URL, headers=HEADERS, timeout=2)
        if response.status_code != 200:
            return None
        dados = response.json()
        novo_id = dados.get("id")
        if not novo_id or novo_id == ultimo_id_latest:
            return None
        ultimo_id_latest = novo_id
        data = dados.get("data", {})
        result = data.get("result", {})
        player_dice = result.get("playerDice", {})
        banker_dice = result.get("bankerDice", {})
        player_score = player_dice.get("first", 0) + player_dice.get("second", 0)
        banker_score = banker_dice.get("first", 0) + banker_dice.get("second", 0)
        outcome = result.get("outcome", "")
        if outcome == "PlayerWon":
            resultado = "PLAYER"
        elif outcome == "BankerWon":
            resultado = "BANKER"
        else:
            resultado = "TIE"
        return {
            "id": novo_id,
            "data_hora": datetime.now(timezone.utc),
            "player_score": player_score,
            "banker_score": banker_score,
            "resultado": resultado,
        }
    except Exception as exc:
        print(f"⚠️ Erro LATEST: {exc}")
        return None


def loop_latest():
    print("📡 Coletor LATEST iniciado...")
    while True:
        try:
            rodada = buscar_latest()
            if rodada:
                fila_rodadas.append(rodada)
            time.sleep(INTERVALO_LATEST)
        except Exception as exc:
            print(f"❌ Erro LATEST: {exc}")
            time.sleep(1)


def processar_fila():
    print("🚀 Processador ENSEMBLE iniciado...")
    historico_buffer = []
    ultima_previsao_feita = None

    while True:
        try:
            if fila_rodadas:
                batch = list(fila_rodadas)
                fila_rodadas.clear()
                for rodada in batch:
                    if not salvar_rodada(rodada, "principal"):
                        continue
                    historico_buffer.append(rodada)
                    cache["ultimo_resultado_real"] = rodada["resultado"]
                    print(f"✅ SALVO: {rodada['player_score']} vs {rodada['banker_score']} - {rodada['resultado']}")

                    if ultima_previsao_feita:
                        resultado_real = rodada["resultado"]
                        if resultado_real != "TIE":
                            acertou = ultima_previsao_feita["previsao"] == resultado_real
                            salvar_previsao(ultima_previsao_feita, resultado_real, acertou, historico_buffer[-50:])
                            cache["estatisticas"]["total_previsoes"] += 1
                            if acertou:
                                cache["estatisticas"]["acertos"] += 1
                            else:
                                cache["estatisticas"]["erros"] += 1
                            if cache.get("ensemble"):
                                cache["ensemble"].aprender(resultado_real)
                            cache["estatisticas"]["ultimas_20_previsoes"].insert(
                                0,
                                {
                                    "data": datetime.now().strftime("%d/%m %H:%M:%S"),
                                    "previsao": ultima_previsao_feita["previsao"],
                                    "simbolo": ultima_previsao_feita["simbolo"],
                                    "confianca": ultima_previsao_feita["confianca"],
                                    "resultado_real": resultado_real,
                                    "acertou": acertou,
                                    "estrategias": ultima_previsao_feita.get("estrategias", []),
                                },
                            )
                            cache["estatisticas"]["ultimas_20_previsoes"] = cache["estatisticas"]["ultimas_20_previsoes"][:20]
                        ultima_previsao_feita = None

                    if len(historico_buffer) >= 30 and cache.get("ensemble") and ultima_previsao_feita is None:
                        historico_completo = [
                            {
                                "player_score": item["player_score"],
                                "banker_score": item["banker_score"],
                                "resultado": item["resultado"],
                            }
                            for item in historico_buffer[-50:]
                        ]
                        previsao = cache["ensemble"].prever(historico_completo)
                        if previsao["previsao"] != "AGUARDANDO":
                            ultima_previsao_feita = {
                                "modo": previsao["modo"],
                                "previsao": previsao["previsao"],
                                "simbolo": previsao["simbolo"],
                                "confianca": previsao["confianca"],
                                "estrategias": previsao.get("estrategias", []),
                            }
                            cache["leves"]["previsao"] = ultima_previsao_feita
                            cache["ultima_previsao"] = ultima_previsao_feita

                    cache["leves"]["ultima_atualizacao"] = datetime.now(timezone.utc)
            time.sleep(0.01)
        except Exception as exc:
            print(f"❌ Erro no processador: {exc}")
            traceback.print_exc()
            time.sleep(0.1)


def atualizar_dados_leves():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("SELECT player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT 50")
        rows = cur.fetchall()
        cache["leves"]["ultimas_50"] = [{"player_score": r[0], "banker_score": r[1], "resultado": r[2]} for r in rows]
        cache["leves"]["ultimas_20"] = cache["leves"]["ultimas_50"][:20]
        cur.execute("SELECT COUNT(*) FROM rodadas")
        cache["leves"]["total_rodadas"] = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"⚠️ Erro atualizar dados: {exc}")


def atualizar_dados_pesados():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        agora = datetime.now(timezone.utc)
        periodos = {
            "10min": agora - timedelta(minutes=10),
            "1h": agora - timedelta(hours=1),
            "6h": agora - timedelta(hours=6),
            "12h": agora - timedelta(hours=12),
            "24h": agora - timedelta(hours=24),
            "48h": agora - timedelta(hours=48),
            "72h": agora - timedelta(hours=72),
        }
        for nome, limite in periodos.items():
            cur.execute("SELECT COUNT(*) FROM rodadas WHERE data_hora >= %s", (limite,))
            cache["pesados"]["periodos"][nome] = cur.fetchone()[0]
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"⚠️ Erro periodos: {exc}")


@app.route("/api/stats")
def api_stats():
    stats_ensemble = cache["ensemble"].get_stats() if cache.get("ensemble") else {}
    agentes_formatados = []
    if stats_ensemble.get("especialistas"):
        for esp in stats_ensemble["especialistas"]:
            agentes_formatados.append(
                {
                    "nome": esp["nome"],
                    "acertos": esp["acertos"],
                    "erros": esp["erros"],
                    "precisao": esp["precisao"],
                    "peso": esp["peso"],
                    "saude": 100,
                    "fitness": esp["precisao"],
                    "especialidade": esp["padrao"],
                }
            )
    return jsonify(
        {
            "ultima_atualizacao": cache["leves"]["ultima_atualizacao"].strftime("%d/%m %H:%M:%S") if cache["leves"]["ultima_atualizacao"] else None,
            "total_rodadas": cache["leves"]["total_rodadas"],
            "ultimas_20": cache["leves"]["ultimas_20"],
            "previsao": cache["leves"]["previsao"],
            "periodos": cache["pesados"]["periodos"],
            "fonte_ativa": "ensemble",
            "estatisticas": {
                "total_previsoes": cache["estatisticas"]["total_previsoes"],
                "acertos": cache["estatisticas"]["acertos"],
                "erros": cache["estatisticas"]["erros"],
                "precisao": calcular_precisao(),
                "ultimas_20_previsoes": cache["estatisticas"]["ultimas_20_previsoes"],
                "estrategias": agentes_formatados,
            },
            "aprendizado": stats_ensemble,
            "ensemble_stats": stats_ensemble,
        }
    )


@app.route("/api/tabela/<int:limite>")
def api_tabela(limite: int):
    limite = min(max(limite, 50), 3000)
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    cur = conn.cursor()
    cur.execute("SELECT data_hora, player_score, banker_score, resultado FROM rodadas ORDER BY data_hora DESC LIMIT %s", (limite,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    resultado = []
    for row in rows:
        data_dt = row[0]
        if data_dt.tzinfo is None:
            data_dt = data_dt.replace(tzinfo=timezone.utc)
        brasilia = data_dt.astimezone(timezone(timedelta(hours=-3)))
        resultado.append(
            {
                "data": brasilia.strftime("%d/%m %H:%M:%S"),
                "player": row[1],
                "banker": row[2],
                "resultado": row[3],
                "cor": "🔴" if row[3] == "BANKER" else "🔵" if row[3] == "PLAYER" else "🟡",
            }
        )
    return jsonify(resultado)


@app.route("/api/aprendizado")
def api_aprendizado():
    if cache.get("ensemble"):
        return jsonify(cache["ensemble"].get_stats())
    return jsonify({"erro": "Ensemble não inicializado"})


@app.route("/api/curto-prazo")
def api_curto_prazo():
    stats = cache["ensemble"].get_stats() if cache.get("ensemble") else {}
    return jsonify(
        {
            "status": "ativo",
            "estatisticas": {
                "ciclo_atual": 0,
                "rodada_no_ciclo": 0,
                "precisao_ciclo_atual": stats.get("precisao", 0),
                "total_ciclos": 0,
                "media_precisao_ciclos": stats.get("precisao", 0),
                "melhor_ciclo": {"precisao": stats.get("precisao", 0)},
            },
            "ultimos_ciclos": [],
        }
    )


def inicializar_sistema():
    print("\n" + "=" * 80)
    print("🚀 INICIALIZANDO SISTEMA BACBO - ENSEMBLE DE AGENTES")
    print("=" * 80)
    cache["indicadores"] = BacBoIndicators()
    cache["mapa_mental"] = MapaMental()
    cache["ensemble"] = EnsembleAgentes(
        indicadores=cache["indicadores"], mapa_mental=cache["mapa_mental"]
    )
    print("\n✅ Sistema inicializado com sucesso!")
    print(f"   🧠 {len(cache['ensemble'].agentes)} especialistas")
    print(f"   🗺️ Mapa mental: {cache['mapa_mental'].get_stats()['total']} memórias")
    print("=" * 80)


if __name__ == "__main__":
    print("=" * 80)
    print("🚀 BACBO PREDICTOR - ENSEMBLE DE AGENTES v10.0")
    print("=" * 80)
    init_db()
    atualizar_dados_leves()
    atualizar_dados_pesados()
    inicializar_sistema()
    threading.Thread(target=loop_latest, daemon=True).start()
    threading.Thread(target=processar_fila, daemon=True).start()

    def loop_atualizacao():
        while True:
            time.sleep(60)
            atualizar_dados_leves()
            atualizar_dados_pesados()

    threading.Thread(target=loop_atualizacao, daemon=True).start()
    print("\n" + "=" * 80)
    print("🚀 FLASK INICIANDO...")
    print("🎯 Sistema ENSEMBLE ATIVO")
    print("🎯 7 especialistas + Mapa Mental")
    print("=" * 80)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
