from flask import Blueprint, render_template, request, jsonify

from app.db import get_db


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    return render_template("recipes.html")

@bp.get("/api/recipeGenerate")
def GenerateRecipes():
    budget = request.args.get("budget", type=int)
    budget += 10
    return jsonify({"budget": budget})

@bp.get("/upload_receipt")
def upload_receipt():

    return render_template("upload_receipt.html")