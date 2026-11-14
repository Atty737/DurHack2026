import os

from dotenv import load_dotenv
from flask import Flask
from pymongo import MongoClient


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "dev"),
        MONGO_URI=os.getenv("MONGO_URI"),
        MONGO_DB_NAME=os.getenv("MONGO_DB_NAME", "durhack2026"),
    )

    if test_config is not None:
        app.config.update(test_config)

    if app.config["MONGO_URI"]:
        mongo_client = MongoClient(app.config["MONGO_URI"])
        app.extensions["mongo_client"] = mongo_client
        app.extensions["mongo_db"] = mongo_client[app.config["MONGO_DB_NAME"]]

    from app.main import bp as main_bp

    app.register_blueprint(main_bp)

    from app.recipes import bp as recipes_bp

    app.register_blueprint(recipes_bp)

    return app
