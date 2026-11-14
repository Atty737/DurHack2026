from flask import Blueprint, render_template


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    return render_template("recipes.html")