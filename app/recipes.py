from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from google import genai
from dotenv import load_dotenv
from app.db import get_db
from pymongo import MongoClient
import json


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    if not session.get("user_id"):
        flash("Log in to view recipes.", "info")
        return redirect(url_for("auth.login"))

    return render_template("recipes.html")


@bp.get("/api/recipeGenerate")
def GenerateRecipes():
    if not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401
    
    items = list(
            get_db().receipt_items.find(
                {"user_id": session["user_id"]},
            ).sort("created_at", -1)
        )
    userItems = []
    for entry in items:
        userItems.append(f"{entry.get("quantity")} {entry.get("item_name")}")

    load_dotenv()
    budget = request.args.get("budget", type=int)
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"Make 7 dinner recipes where the ingredients total to under £{budget} and try to use these items they already have but you don't have to use all of them and keep the recipes interesting and different {userItems}, return as text in a JSON format (with no ` or json at the start or end) as a list where each list is in the format [recipe_name, [List of ingredients with relevant units], the recipe instructions as a string formatted in steps with each being seperated by '\\n'"
    )

    recipes = json.loads(response.text)
    recipeNames = [recipes[0][0], recipes[1][0], recipes[2][0], recipes[3][0], recipes[4][0], recipes[5][0], recipes[6][0]]
    ingredients = [recipes[0][1], recipes[1][1], recipes[2][1], recipes[3][1], recipes[4][1], recipes[5][1], recipes[6][1]]
    links = [recipes[0][2], recipes[1][2], recipes[2][2], recipes[3][2], recipes[4][2], recipes[5][2], recipes[6][2]]
    return jsonify({"recipeNames": recipeNames, "ingredients": ingredients, "links": links})
