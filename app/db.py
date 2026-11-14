from flask import current_app
from pymongo import MongoClient
from pymongo.database import Database


def init_app(app):
    mongo_uri = app.config.get("MONGO_URI")
    if not mongo_uri:
        return

    client = MongoClient(mongo_uri)
    app.extensions["mongo_client"] = client
    app.extensions["mongo_db"] = client[app.config["MONGO_DB_NAME"]]


def get_db() -> Database:
    database = current_app.extensions.get("mongo_db")
    if database is None:
        raise RuntimeError(
            "MongoDB is not configured. Set MONGO_URI in the environment."
        )
    return database
