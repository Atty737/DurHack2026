from flask import Blueprint, jsonify, render_template

from app.db import get_db


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    return render_template("recipes.html")


@bp.get("/api/recipes")
def list_recipes():
    recipes = get_db().recipes.find({}, {"_id": 0})
    return jsonify(list(recipes))