from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from google import genai
from dotenv import load_dotenv
from app.db import get_db


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

    load_dotenv()
    budget = request.args.get("budget", type=int)
    client = genai.Client()

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=f"Make 7 dinner recipes where the ingredients total to under £{budget}, include the name of each dish followed by a list of the ingredients and then the instructions to make it",
    )
    return jsonify({"response": response.text})
