"""Ponto de entrada alternativo para servir a interface web."""

from app import create_app, init_system

app = create_app()
init_system()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
