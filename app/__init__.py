"""
Aplicação BacBo Predictor - Versão Ensemble.
"""

import os
import sys

from flask import Flask, render_template
from flask_cors import CORS

# Adicionar diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.ml.ensemble import EnsembleAgentes
from app.ml.indicators import BacBoIndicators
from app.ml.memory_map import MapaMental

cache = {
    "ensemble": None,
    "mapa_mental": None,
    "indicadores": None,
}


def create_app() -> Flask:
    """Cria e configura a aplicação Flask."""
    app = Flask(__name__, static_folder="static", template_folder="templates")
    CORS(app)

    @app.route("/health")
    def health():
        return {"status": "ok", "ensemble": cache["ensemble"] is not None}

    @app.route("/")
    def index():
        return render_template("index.html")

    return app


def init_system() -> EnsembleAgentes:
    """Inicializa o sistema Ensemble."""
    print("\n" + "=" * 80)
    print("🎯 INICIALIZANDO SISTEMA ENSEMBLE")
    print("=" * 80)

    cache["indicadores"] = BacBoIndicators()
    cache["mapa_mental"] = MapaMental()
    cache["ensemble"] = EnsembleAgentes(
        indicadores=cache["indicadores"],
        mapa_mental=cache["mapa_mental"],
    )

    print("\n✅ Sistema inicializado com sucesso!")
    print(f"   🧠 Ensemble: {len(cache['ensemble'].agentes)} especialistas")
    print(f"   🗺️ Mapa Mental: {cache['mapa_mental'].get_stats()['total']} memórias")
    print("=" * 80)

    return cache["ensemble"]
