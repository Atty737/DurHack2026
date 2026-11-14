from flask import Blueprint, render_template, request, jsonify
from google import genai
from dotenv import load_dotenv
from app.db import get_db
import json


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    return render_template("recipes.html")

@bp.get("/api/recipeGenerate")
def GenerateRecipes():
    load_dotenv()
    budget = request.args.get("budget", type=int)
    client = genai.Client(api_key = "AQ.Ab8RN6LY4yfu-pudz8qrOU4_23uWMJ99OgnVOAzXoXfOWg1Zqw")

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"Make 7 dinner recipes where the ingredients total to under £{budget}, return as text in a JSON format (with no ` or json at the start or end) as a list where each list is in the format [recipe_name, [List of ingredients with relevant units], the recipe instructions as a string]"
    )
    recipes = json.loads(response.text)
    recipeNames = [recipes[0][0], recipes[1][0], recipes[2][0], recipes[3][0], recipes[4][0], recipes[5][0], recipes[6][0]]
    ingredients = [recipes[0][1], recipes[1][1], recipes[2][1], recipes[3][1], recipes[4][1], recipes[5][1], recipes[6][1]]
    links = [recipes[0][2], recipes[1][2], recipes[2][2], recipes[3][2], recipes[4][2], recipes[5][2], recipes[6][2]]
    return jsonify({"recipeNames": recipeNames, "ingredients": ingredients, "links": links})