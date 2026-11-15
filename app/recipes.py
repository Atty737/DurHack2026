from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from google import genai
from dotenv import load_dotenv
from app.db import get_db
from datetime import datetime, timezone
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
        userItems.append(f"{entry.get('quantity')} {entry.get('item_name')}")

    load_dotenv()
    budget = request.args.get("budget", type=int)
    client = genai.Client()
    prompt = f"""
    Make 7 savoury dinner recipes (meals to feed one person, SUFFICIENTLY for an evening) 
    where the ingredients total to under £{budget} and which can include these items they already have 
    but you don't have to use all of them and keep the recipes interesting and different by potentially 
    using items not in there {userItems}. In the list, give the weight of the ingredient needed, NOT the weight in {userItems}. 
    Additionally, you don't have to use the exact name which is given in the {userItems} (e.g. Tesco Finest Loose Potatoes), 
    just say '<weight> potatoes'. Don't use the same ingredient in any two meals. Do NOT, under ANY circumstances use the name 
    of a supermarket or brand in the list. Return as text in a JSON format (with no ` or json at the start or end) as a list 
    where each list is in the format:
    """ + """
    [{
        'recipe_name': <recipe_name>,
        'ingredients': [List of ingredients with relevant units],
        'instructions': [List of instructions],

    }, ...
    ]
    """
    
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt
    )

    while not tryCall(response):
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt
        )

    recipes = json.loads(response.text)

    items = []
    for recipe in recipes:
        items.append(
            {
                "user_id": session["user_id"],
                "recipe_name": recipe["recipe_name"], 
                "ingredients": recipe["ingredients"], 
                "recipe": recipe["instructions"], 
                "created_at": datetime.now(timezone.utc)
            }
        )
    
    if items:
        get_db().recipes.insert_many(items)
        for item in items:
            item["_id"] = str(item["_id"])

    return jsonify(items)

def tryCall(response):
    try:
        json.loads(response.text)
        return True
    except Exception:
        return False
