"""
Aplicação BacBo Predictor - Versão Ensemble Evolutivo
"""

import os
import sys

# Adicionar diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from flask_cors import CORS

from app.ml.ensemble import EnsembleEvolutivo
from app.ml.indicators import BacBoIndicators
from app.ml.memory_map import MapaMental

cache = {
    'ensemble': None,
    'mapa_mental': None,
    'indicadores': None
}


def create_app():
    """Cria e configura a aplicação Flask"""
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='templates',
    )
    CORS(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'ensemble': cache['ensemble'] is not None}

    @app.route('/')
    def index():
        from flask import render_template
        return render_template('index.html')

    return app


def init_system():
    """Inicializa o sistema Ensemble Evolutivo"""
    print("\n" + "=" * 80)
    print("🎯 INICIALIZANDO SISTEMA ENSEMBLE EVOLUTIVO")
    print("=" * 80)

    cache['indicadores'] = BacBoIndicators()
    cache['mapa_mental'] = MapaMental()
    cache['ensemble'] = EnsembleEvolutivo()

    stats = cache['ensemble'].get_stats()

    print("\n✅ Sistema inicializado com sucesso!")
    print(f"   🧠 {stats['total_agentes']} especialistas (começou com 7, vai crescer!)")
    print(f"   🗺️ Mapa mental: {stats['mapa_mental']['total']} memórias")
    print(f"   📈 Precisão atual: {stats['precisao']}%")
    print("=" * 80)

    return cache['ensemble']
