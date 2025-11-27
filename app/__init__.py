from flask import Flask
from app.config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Blueprints
    from app.controllers.telemetria_controller import bp as telemetria_bp
    app.register_blueprint(telemetria_bp)

    @app.route("/")
    def health():
        return {"status": "ok"}

    return app
