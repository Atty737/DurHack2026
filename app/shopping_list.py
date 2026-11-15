from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from app.db import get_db
from app.gemini_image import clean_ingredient_name, standardize_unit_and_amount

bp = Blueprint("shopping_list", __name__)


def sync_missing_recipe_items_to_shopping_list(user_id: str, db) -> int:
    """Scan all saved recipes for a user and add missing ingredients to the shopping list."""
    recipes = list(db.recipes.find({"user_id": user_id}))
    if not recipes:
        return 0

    pantry_ids = {
        str(doc["_id"])
        for doc in db.receipt_items.find({"user_id": user_id}, {"_id": 1})
    }

    existing_items = list(db.shopping_list.find({"user_id": user_id}))
    existing_keys = {
        (
            str(item.get("recipe_id") or ""),
            (item.get("item_name") or "").strip().lower(),
        )
        for item in existing_items
    }

    new_items = []
    for recipe in recipes:
        recipe_id = recipe["_id"]
        recipe_name = recipe.get("recipe_name", "Recipe")
        for ing in (recipe.get("ingredients") or []):
            if isinstance(ing, dict):
                in_pantry = bool(ing.get("in_pantry")) and (ing.get("pantry_item_id") in pantry_ids)
                raw_name = ing.get("name") or ing.get("item") or "Item"
                amt = ing.get("amount")
                unit = ing.get("unit")
            else:
                in_pantry = False
                raw_name = str(ing)
                amt = None
                unit = "qty"

            if not in_pantry:
                cleaned_name = clean_ingredient_name(raw_name, amt, unit) or raw_name
                dedup_key = (str(recipe_id), cleaned_name.strip().lower())
                if dedup_key not in existing_keys:
                    existing_keys.add(dedup_key)
                    new_items.append({
                        "user_id": user_id,
                        "item_name": cleaned_name,
                        "raw_name": raw_name,
                        "amount": amt,
                        "unit": unit or "qty",
                        "recipe_id": recipe_id,
                        "recipe_name": recipe_name,
                        "checked": False,
                        "created_at": datetime.now(timezone.utc),
                    })

    if new_items:
        db.shopping_list.insert_many(new_items)

    return len(new_items)


@bp.get("/shopping-list")
@bp.get("/shopping_list")
def shopping_list():
    if not session.get("user_id"):
        flash("Log in to view your shopping list.", "info")
        return redirect(url_for("auth.login"))

    db = get_db()
    user_id = session["user_id"]

    items_cursor = list(
        db.shopping_list.find({"user_id": user_id}).sort("created_at", -1)
    )

    # Sort: unchecked first, then checked; both maintain recency order
    unchecked_items = [i for i in items_cursor if not i.get("checked")]
    checked_items = [i for i in items_cursor if i.get("checked")]
    sorted_items = unchecked_items + checked_items

    # Check if user has saved recipes to offer a helpful sync hint if list is empty
    saved_recipe_count = db.recipes.count_documents({"user_id": user_id})

    return render_template(
        "shopping_list.html",
        items=sorted_items,
        total_count=len(sorted_items),
        unchecked_count=len(unchecked_items),
        checked_count=len(checked_items),
        saved_recipe_count=saved_recipe_count,
    )


@bp.post("/shopping-list/add")
def add_item():
    if not session.get("user_id"):
        flash("Log in to update your shopping list.", "info")
        return redirect(url_for("auth.login"))

    item_name = (request.form.get("item_name") or "").strip()
    if not item_name:
        flash("Please enter an item name.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    raw_amt = request.form.get("amount")
    raw_unit = (request.form.get("unit") or "qty").strip()

    if raw_amt and raw_amt.strip():
        std_amt, std_unit = standardize_unit_and_amount(raw_amt.strip(), raw_unit)
    else:
        std_amt, std_unit = None, (raw_unit or "qty")

    cleaned_name = clean_ingredient_name(item_name, std_amt, std_unit) or item_name

    get_db().shopping_list.insert_one({
        "user_id": session["user_id"],
        "item_name": cleaned_name,
        "amount": std_amt,
        "unit": std_unit,
        "recipe_id": None,
        "recipe_name": None,
        "checked": False,
        "created_at": datetime.now(timezone.utc),
    })

    flash(f"Added '{cleaned_name}' to your shopping list.", "success")
    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/<item_id>/toggle")
def toggle_item(item_id):
    if not session.get("user_id"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 401
        flash("Log in to update your shopping list.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        if request.is_json:
            return jsonify({"error": "Invalid ID"}), 400
        flash("That item does not exist.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    db = get_db()
    item = db.shopping_list.find_one({"_id": object_id, "user_id": session["user_id"]})
    if not item:
        if request.is_json:
            return jsonify({"error": "Item not found"}), 404
        flash("That item does not exist.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    new_state = not bool(item.get("checked", False))
    db.shopping_list.update_one(
        {"_id": object_id, "user_id": session["user_id"]},
        {"$set": {"checked": new_state}}
    )

    if request.is_json:
        return jsonify({"success": True, "checked": new_state})

    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/<item_id>/delete")
def delete_item(item_id):
    if not session.get("user_id"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 401
        flash("Log in to update your shopping list.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        if request.is_json:
            return jsonify({"error": "Invalid ID"}), 400
        flash("That item does not exist.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    result = get_db().shopping_list.delete_one(
        {"_id": object_id, "user_id": session["user_id"]}
    )

    if request.is_json:
        return jsonify({"success": bool(result.deleted_count)})

    if result.deleted_count:
        flash("Item removed from your shopping list.", "info")
    else:
        flash("That item does not exist.", "warning")

    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/<item_id>/move-to-pantry")
def move_to_pantry(item_id):
    if not session.get("user_id"):
        if request.is_json:
            return jsonify({"error": "Unauthorized"}), 401
        flash("Log in to update your pantry.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        if request.is_json:
            return jsonify({"error": "Invalid ID"}), 400
        flash("That item does not exist.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    db = get_db()
    item = db.shopping_list.find_one({"_id": object_id, "user_id": session["user_id"]})
    if not item:
        if request.is_json:
            return jsonify({"error": "Item not found"}), 404
        flash("That item does not exist.", "warning")
        return redirect(url_for("shopping_list.shopping_list"))

    raw_amt = item.get("amount")
    unit = item.get("unit") or "qty"
    if raw_amt is not None:
        std_amt, std_unit = standardize_unit_and_amount(raw_amt, unit)
    else:
        std_amt, std_unit = 1, unit

    # Insert into receipt_items collection (pantry)
    pantry_res = db.receipt_items.insert_one({
        "user_id": session["user_id"],
        "receipt_id": "shopping_list",
        "item_name": item["item_name"],
        "price": None,
        "amount": std_amt,
        "quantity": std_amt,
        "unit": std_unit,
        "created_at": datetime.now(timezone.utc),
    })
    new_pantry_id = str(pantry_res.inserted_id)

    # Track and update recipe ingredients: change from 'Need to buy' to 'In pantry'
    target_clean = (item.get("item_name") or "").strip().lower()
    target_raw = (item.get("raw_name") or "").strip().lower()

    recipe_oid = None
    if item.get("recipe_id"):
        try:
            recipe_oid = ObjectId(item["recipe_id"])
        except (InvalidId, TypeError):
            pass

    user_recipes = list(db.recipes.find({"user_id": session["user_id"]}))
    for rec in user_recipes:
        is_origin_recipe = (recipe_oid is not None and rec["_id"] == recipe_oid)
        recipe_modified = False
        ingredients = rec.get("ingredients") or []

        for ing in ingredients:
            if isinstance(ing, dict) and not ing.get("in_pantry"):
                ing_name = (ing.get("name") or ing.get("item") or "").strip()
                ing_raw_lower = ing_name.lower()
                ing_clean = clean_ingredient_name(ing_name, ing.get("amount"), ing.get("unit")).strip().lower()

                matched = False
                if is_origin_recipe:
                    if (target_raw and target_raw == ing_raw_lower) or (target_clean and (target_clean == ing_clean or target_clean in ing_raw_lower)):
                        matched = True
                else:
                    if (target_clean and target_clean == ing_clean) or (target_raw and target_raw == ing_raw_lower):
                        matched = True

                if matched:
                    ing["in_pantry"] = True
                    ing["pantry_item_id"] = new_pantry_id
                    recipe_modified = True

        if recipe_modified:
            db.recipes.update_one(
                {"_id": rec["_id"], "user_id": session["user_id"]},
                {"$set": {"ingredients": ingredients}}
            )

    # Remove from shopping list
    db.shopping_list.delete_one({"_id": object_id, "user_id": session["user_id"]})

    msg = f"Added '{item['item_name']}' ({std_amt} {std_unit}) to your pantry!"
    if request.is_json:
        return jsonify({"success": True, "message": msg})

    flash(msg, "success")
    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/clear-checked")
def clear_checked():
    if not session.get("user_id"):
        flash("Log in to update your shopping list.", "info")
        return redirect(url_for("auth.login"))

    result = get_db().shopping_list.delete_many(
        {"user_id": session["user_id"], "checked": True}
    )
    flash(f"Removed {result.deleted_count} completed item(s).", "info")
    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/clear-all")
def clear_all():
    if not session.get("user_id"):
        flash("Log in to update your shopping list.", "info")
        return redirect(url_for("auth.login"))

    result = get_db().shopping_list.delete_many({"user_id": session["user_id"]})
    flash(f"Cleared all {result.deleted_count} item(s) from your shopping list.", "info")
    return redirect(url_for("shopping_list.shopping_list"))


@bp.post("/shopping-list/sync-saved-recipes")
def sync_saved_recipes():
    if not session.get("user_id"):
        flash("Log in to sync your shopping list.", "info")
        return redirect(url_for("auth.login"))

    added = sync_missing_recipe_items_to_shopping_list(session["user_id"], get_db())
    if added > 0:
        flash(f"Added {added} missing item{'s' if added != 1 else ''} from your saved recipes to your shopping list.", "success")
    else:
        flash("Your shopping list is already up to date with your saved recipes.", "info")

    return redirect(url_for("shopping_list.shopping_list"))
