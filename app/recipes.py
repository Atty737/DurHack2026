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
        flash("Log in to view recipes.")
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
        contents=f"Make 7 savoury dinner recipes (meals to feed one person, SUFFICIENTLY for an evening) where the ingredients total to under £{budget} and which can include these items they already have but you don't have to use all of them and keep the recipes interesting and different by potentially using items not in there {userItems}. In the list, give the weight of the ingredient needed, NOT the weight in {userItems}. Additionally, you don't have to use the exact name which is given in the {userItems} (e.g. Tesco Finest Loose Potatoes), just say '<weight> potatoes'. Don't use the same ingredient in any two meals. Do NOT, under ANY circumstances use the name of a supermarket or brand in the list. Return as text in a JSON format (with no ` or json at the start or end) as a list where each list is in the format [recipe_name, [List of ingredients with relevant units], the recipe instructions as a string formatted in steps with each being seperated by '\n'"
    )

    recipes = json.loads(response.text)
    recipeNames = [recipes[0][0], recipes[1][0], recipes[2][0], recipes[3][0], recipes[4][0], recipes[5][0], recipes[6][0]]
    ingredients = [recipes[0][1], recipes[1][1], recipes[2][1], recipes[3][1], recipes[4][1], recipes[5][1], recipes[6][1]]
    links = [recipes[0][2], recipes[1][2], recipes[2][2], recipes[3][2], recipes[4][2], recipes[5][2], recipes[6][2]]
    return jsonify({"recipeNames": recipeNames, "ingredients": ingredients, "links": links})
