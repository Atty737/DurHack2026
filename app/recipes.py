import json
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from flask import Blueprint, flash, redirect, render_template, request, session, url_for, jsonify
from google import genai
from google.genai import errors
from app.db import get_db
from app.gemini_image import standardize_unit_and_amount, format_gemini_error, clean_ingredient_name


bp = Blueprint("recipes", __name__)


@bp.get("/recipes")
def recipes():
    if not session.get("user_id"):
        flash("Log in to view recipes.", "info")
        return redirect(url_for("auth.login"))

    return render_template("recipes.html")


def clean_json_text(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def tryCall(response):
    try:
        data = json.loads(clean_json_text(response.text))
        return isinstance(data, list) and len(data) > 0
    except Exception:
        return False


def match_ingredient_to_pantry(ing_name: str, pantry_by_id: dict) -> str | None:
    """Fuzzy/token fallback to match an ingredient text to a pantry item ID."""
    if not ing_name or not pantry_by_id:
        return None

    raw_words = re.sub(r"[^a-zA-Z\s]", " ", ing_name).lower().split()
    stop_words = {
        "the", "and", "with", "for", "cup", "tbsp", "tsp", "tin", "can",
        "slice", "slices", "pack", "gram", "grams", "pinch", "salt", "pepper",
        "oil", "water", "fresh", "dried", "chopped", "diced", "sliced", "minced",
        "of", "to", "taste", "large", "small", "medium", "half", "clove", "cloves",
        "juice", "zest"
    }
    ing_words = [w for w in raw_words if len(w) > 2 and w not in stop_words]
    ing_text = " " + " ".join(ing_words) + " "

    for item_id, item in pantry_by_id.items():
        pantry_name = (item.get("item_name") or "").lower().strip()
        pantry_words = [
            w for w in re.sub(r"[^a-zA-Z\s]", " ", pantry_name).split()
            if len(w) > 2 and w not in stop_words
        ]

        # Exact token match or singular/plural (e.g. lemon <-> lemons, tomato <-> tomatoes)
        for pw in pantry_words:
            pw_sing = pw[:-1] if pw.endswith("s") and not pw.endswith("ss") else pw
            if pw in ing_words:
                return item_id
            for iw in ing_words:
                iw_sing = iw[:-1] if iw.endswith("s") and not iw.endswith("ss") else iw
                if pw_sing == iw_sing or pw == iw_sing or iw == pw_sing:
                    return item_id

        # Substring phrase match (e.g. "chicken breast" inside "250g chicken breast")
        cleaned_pantry = " ".join(pantry_words)
        if cleaned_pantry and cleaned_pantry in ing_text:
            return item_id

    return None


@bp.get("/api/recipeGenerate")
def GenerateRecipes():
    if not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401

    items_cursor = list(
        get_db().receipt_items.find(
            {"user_id": session["user_id"]},
        ).sort("created_at", -1)
    )

    pantry_by_id = {}
    pantry_items_list = []
    for entry in items_cursor:
        item_id = str(entry["_id"])
        name = (entry.get("item_name") or "").strip()
        if not name:
            continue
        pantry_by_id[item_id] = entry
        amount = entry.get("amount") if entry.get("amount") is not None else entry.get("quantity")
        unit = (entry.get("unit") or "").strip()
        std_amt, std_unit = standardize_unit_and_amount(amount, unit)
        pantry_items_list.append(f"- ID: {item_id} | Name: {name} | Available: {std_amt} {std_unit}")

    pantry_description = "\n".join(pantry_items_list) if pantry_items_list else "None (user pantry is empty)"

    load_dotenv()
    budget = request.args.get("budget", type=int) or 30
    client = genai.Client()

    prompt = f"""
Make 7 savoury dinner recipes (meals to feed one person sufficiently for an evening) 
where the ingredients the user needs to buy total to under £{budget}.

The user already has the following items in their pantry with their exact database ID, name, and available amount:
{pantry_description}

Requirements:
1. You may incorporate items from the user's pantry, but you do not need to use all of them. Keep recipes varied and interesting.
2. In the ingredients list, state the portion/weight needed for that specific meal.
   For EACH ingredient, provide:
   - "name": readable name with amount and units (e.g. "250g Chicken Breast", "1 Lemon", "150ml Milk", "2 Eggs")
   - "amount": the numeric portion amount needed for this meal (e.g. 250, 1, 150, 2)
   - "unit": MUST strictly be one of these standard units: "g", "ml", "qty". Always convert non-standard units (e.g. convert kg to g, litres/pints/cups/tbsp to ml, whole items/counts/tins to qty).
   - "in_pantry": true if user has this item in their pantry, false if they need to purchase it
   - "pantry_item_id": exact ID string from the pantry list above if in_pantry is true, null if in_pantry is false.
3. Do NOT use supermarket or commercial brand names.
4. For EACH ingredient in every recipe:
   - If the ingredient uses an item from the user's pantry (even if phrased slightly differently, e.g. singular vs plural like '1 lemon' or 'juice of 1 lemon' matching pantry item 'lemons', or '200g chicken' matching 'chicken breast'), you MUST mark 'in_pantry': true AND set 'pantry_item_id' to the exact database ID string of that pantry item from the list above.
   - If the ingredient is NOT in the user's pantry and needs to be bought at the store, you MUST mark 'in_pantry': false AND set 'pantry_item_id': null.
   - Do NOT invent or make up IDs. Only use an exact ID string from the pantry list above when in_pantry is true.

Return ONLY a valid JSON array of 7 recipe objects with NO surrounding markdown or backticks in this exact schema:
[
  {{
    "recipe_name": "<recipe_name>",
    "ingredients": [
      {{"name": "250g Chicken Breast", "amount": 250, "unit": "g", "in_pantry": true, "pantry_item_id": "<exact ID string from pantry>"}},
      {{"name": "100g Spinach", "amount": 100, "unit": "g", "in_pantry": false, "pantry_item_id": null}}
    ],
    "instructions": [
      "<step 1 instruction>",
      "<step 2 instruction>"
    ]
  }}
]
"""

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
        )

        attempts = 0
        while not tryCall(response) and attempts < 3:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
            )
            attempts += 1

        if not tryCall(response):
            err_msg = "Gemini could not generate recipes in the expected format. Please try again."
            flash(err_msg, "warning")
            return jsonify({"error": err_msg}), 502

        recipes = json.loads(clean_json_text(response.text))
    except errors.APIError as error:
        err_msg = format_gemini_error(error)
        flash(err_msg, "danger")
        status_code = getattr(error, "code", 503) or 503
        return jsonify({"error": err_msg}), status_code
    except Exception as error:
        err_msg = format_gemini_error(error)
        flash(err_msg, "danger")
        return jsonify({"error": err_msg}), 500

    items = []
    for recipe in recipes:
        formatted_ingredients = []
        for ing in recipe.get("ingredients", []):
            if isinstance(ing, dict):
                ing_name = ing.get("name") or ing.get("item") or ""
                raw_pid = ing.get("pantry_item_id")
                matched_id = None

                if raw_pid and str(raw_pid).strip() in pantry_by_id:
                    matched_id = str(raw_pid).strip()
                    in_pantry = True
                else:
                    # Fallback token matching if Gemini omitted the ID or mislabeled
                    fallback_id = match_ingredient_to_pantry(ing_name, pantry_by_id)
                    if fallback_id:
                        matched_id = fallback_id
                        in_pantry = True
                    else:
                        in_pantry = bool(ing.get("in_pantry", False))

                raw_amt = ing.get("amount")
                raw_unit = ing.get("unit")
                if raw_amt is not None:
                    std_amt, std_unit = standardize_unit_and_amount(raw_amt, raw_unit)
                else:
                    std_amt, std_unit = None, "qty"

                formatted_ingredients.append({
                    "name": ing_name,
                    "amount": std_amt,
                    "unit": std_unit,
                    "in_pantry": in_pantry,
                    "pantry_item_id": matched_id,
                })
            elif isinstance(ing, str):
                fallback_id = match_ingredient_to_pantry(ing, pantry_by_id)
                formatted_ingredients.append({
                    "name": ing,
                    "amount": None,
                    "unit": "qty",
                    "in_pantry": fallback_id is not None,
                    "pantry_item_id": fallback_id,
                })

        items.append({
            "recipe_name": recipe.get("recipe_name", "Untitled Recipe"),
            "ingredients": formatted_ingredients,
            "recipe": recipe.get("instructions", []),
        })

    return jsonify(items)


@bp.post("/api/saveRecipe")
@bp.post("/api/recipes/save")
def save_recipe():
    if not session.get("user_id"):
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    recipe_name = data.get("recipe_name")
    ingredients = data.get("ingredients")
    recipe_instructions = data.get("instructions") or data.get("recipe")

    if not recipe_name:
        return jsonify({"error": "Missing recipe name"}), 400

    sanitized_ingredients = []
    for ing in (ingredients or []):
        if isinstance(ing, dict):
            pid = ing.get("pantry_item_id")
            raw_amt = ing.get("amount")
            raw_unit = ing.get("unit")
            if raw_amt is not None:
                std_amt, std_unit = standardize_unit_and_amount(raw_amt, raw_unit)
            else:
                std_amt, std_unit = None, "qty"

            sanitized_ingredients.append({
                "name": ing.get("name") or ing.get("item") or "",
                "amount": std_amt,
                "unit": std_unit,
                "in_pantry": bool(ing.get("in_pantry", False)),
                "pantry_item_id": str(pid).strip() if pid else None,
            })
        else:
            sanitized_ingredients.append({
                "name": str(ing),
                "amount": None,
                "unit": "qty",
                "in_pantry": False,
                "pantry_item_id": None,
            })

    item = {
        "user_id": session["user_id"],
        "recipe_name": recipe_name,
        "ingredients": sanitized_ingredients,
        "recipe": recipe_instructions or [],
        "created_at": datetime.now(timezone.utc),
    }

    result = get_db().recipes.insert_one(item)

    # Automatically add ingredients not in pantry to shopping list
    user_pantry_ids = {
        str(doc["_id"])
        for doc in get_db().receipt_items.find({"user_id": session["user_id"]}, {"_id": 1})
    }

    shopping_items = []
    for ing in sanitized_ingredients:
        # Check if ingredient is truly in pantry
        in_pantry = bool(ing.get("in_pantry")) and (ing.get("pantry_item_id") in user_pantry_ids)
        if not in_pantry:
            raw_name = ing.get("name") or "Item"
            cleaned_name = clean_ingredient_name(raw_name, ing.get("amount"), ing.get("unit"))
            shopping_items.append({
                "user_id": session["user_id"],
                "item_name": cleaned_name or raw_name,
                "raw_name": raw_name,
                "amount": ing.get("amount"),
                "unit": ing.get("unit") or "qty",
                "recipe_id": result.inserted_id,
                "recipe_name": recipe_name,
                "checked": False,
                "created_at": datetime.now(timezone.utc),
            })

    if shopping_items:
        get_db().shopping_list.insert_many(shopping_items)

    added_count = len(shopping_items)
    if added_count > 0:
        msg = f"Saved '{recipe_name}' to your recipes and added {added_count} missing item{'s' if added_count != 1 else ''} to your shopping list."
    else:
        msg = f"Saved '{recipe_name}' to your recipes."

    return jsonify(
        {
            "success": True,
            "recipe_id": str(result.inserted_id),
            "added_to_shopping_list": added_count,
            "message": msg,
        }
    )
