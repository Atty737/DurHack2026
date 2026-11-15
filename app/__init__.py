import os

import click
from dotenv import load_dotenv
from flask import Flask

from app.db import init_app as init_db
from app.db import get_db
from app.migrations import run as run_migrations


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        MONGO_URI=os.getenv("MONGO_URI"),
        MONGO_DB_NAME=os.getenv("MONGO_DB_NAME", "durhack2026"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )

    if test_config is not None:
        app.config.update(test_config)

    init_db(app)

    @app.cli.command("init-db")
    def init_db_command():
        """Create MongoDB collections and indexes required by the app."""
        run_migrations(get_db())
        click.echo("MongoDB initialized.")

    from app.main import bp as main_bp
    from app.auth import bp as auth_bp
    from app.receipts import bp as receipts_bp
    from app.recipes import bp as recipes_bp
    from app.recipe_menu import bp as recipe_menu_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(receipts_bp)
    app.register_blueprint(recipes_bp)
    app.register_blueprint(recipe_menu_bp)
    
    return app
