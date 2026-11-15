import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from bson import ObjectId
from bson.errors import InvalidId
import pytesseract
from werkzeug.utils import secure_filename

from app.db import get_db
from app.gemini_image import gemini_read_image

bp = Blueprint("recipe_menu", __name__)

@bp.get("/recipe_menu")
def recipe_menu():
    if not session.get("user_id"):
        flash("Log in to view your recipes.", "info")
        return redirect(url_for("auth.login"))

    items = list(
        get_db().recipes.find(
            {"user_id": session["user_id"]},
        ).sort("created_at", -1)
    )
    return render_template("recipe_menu.html", items=items)


@bp.post("/recipe_menu/<item_id>/delete")
def delete_recipe(item_id):
    if not session.get("user_id"):
        flash("Log in to delete recipes.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        flash("That recipe does not exist.", "warning")
        return redirect(url_for("recipe_menu.recipe_menu"))

    result = get_db().recipes.delete_one(
        {"_id": object_id, "user_id": session["user_id"]}
    )
    if result.deleted_count:
        flash("Recipe deleted.", "success")
    else:
        flash("That recipe does not exist.", "warning")

    return redirect(url_for("recipe_menu.recipe_menu"))


@bp.post("/recipe-menu/delete-all")
def delete_all_recipes():
    if not session.get("user_id"):
        flash("Log in to delete recipes.", "info")
        return redirect(url_for("auth.login"))

    result = get_db().recipes.delete_many(
        {"user_id": session["user_id"]}
    )
    flash(f"Deleted {result.deleted_count} item(s) from your recipes.", "success")
    return redirect(url_for("recipe_menu.recipe_menu"))
