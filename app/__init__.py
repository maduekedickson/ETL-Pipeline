from flask import Flask, render_template
from flask_cors import CORS
from app.config import Config

def create_app(config_class=Config):
    """Application factory for RiteClick ETL Web App."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app)

    # Register Blueprints
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("500.html"), 500

    @app.errorhandler(413)
    def request_entity_too_large(e):
        return render_template("413.html"), 413

    return app
