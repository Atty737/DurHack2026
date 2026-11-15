import re
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from bson import ObjectId
from bson.errors import InvalidId
from app.db import get_db
from app.gemini_image import standardize_unit_and_amount, clean_ingredient_name

bp = Blueprint("recipe_menu", __name__)


def find_matching_pantry_items(recipe_ingredients, pantry_items):
    """Identify which pantry items match the ingredients of a cooked recipe.
    Uses exact database ID tracking first, falling back to singular/plural token matching."""
    tracked_ids = set()
    matched_ingredient_map = {}

    for ing in recipe_ingredients:
        if isinstance(ing, dict):
            pid = ing.get("pantry_item_id")
            if pid:
                pid_str = str(pid).strip()
                tracked_ids.add(pid_str)
                matched_ingredient_map.setdefault(pid_str, []).append(ing)

    likely_used = []
    other = []

    # Fallback words for ingredients without a pantry_item_id
    fallback_words = set()
    for ing in recipe_ingredients:
        if isinstance(ing, dict):
            if ing.get("pantry_item_id"):
                continue
            text = ing.get("name", "")
        else:
            text = str(ing)
        words = re.sub(r"[^a-zA-Z\s]", " ", text).lower().split()
        for w in words:
            if len(w) > 2 and w not in {
                "the", "and", "with", "for", "cup", "tbsp", "tsp", "tin", "can",
                "slice", "slices", "pack", "gram", "grams", "pinch", "salt", "pepper", "oil"
            }:
                fallback_words.add(w)

    for item in pantry_items:
        item_id_str = str(item["_id"])
        raw_amt = item.get("amount") if item.get("amount") is not None else item.get("quantity")
        pantry_amt, pantry_unit = standardize_unit_and_amount(raw_amt, item.get("unit"))

        if item_id_str in tracked_ids:
            matched_ings = matched_ingredient_map.get(item_id_str, [])
            recipe_names = [i.get("name", "") if isinstance(i, dict) else str(i) for i in matched_ings]

            # Calculate suggested remaining amount based on recipe ingredient amount
            suggested_amount = pantry_amt
            used_amount_note = None

            total_used = 0
            has_numeric_used = False
            for i in matched_ings:
                if isinstance(i, dict) and i.get("amount") is not None:
                    ing_amt, ing_unit = standardize_unit_and_amount(i.get("amount"), i.get("unit"))
                    if ing_unit == pantry_unit:
                        total_used += ing_amt
                        has_numeric_used = True

            if has_numeric_used:
                rem = round(max(0, pantry_amt - total_used), 2)
                suggested_amount = int(rem) if (isinstance(rem, float) and rem.is_integer()) else rem
                used_amount_note = f"Recipe calls for {total_used} {pantry_unit} (you had {pantry_amt} {pantry_unit})"

            item_copy = dict(item)
            item_copy["amount"] = pantry_amt
            item_copy["unit"] = pantry_unit
            item_copy["matched_recipe_ingredients"] = recipe_names
            item_copy["suggested_amount"] = suggested_amount
            item_copy["used_amount_note"] = used_amount_note
            likely_used.append(item_copy)
        else:
            item_words = re.sub(r"[^a-zA-Z\s]", " ", item.get("item_name", "")).lower().split()
            matched = False
            for w in item_words:
                if len(w) > 2:
                    if w in fallback_words:
                        matched = True
                        break
                    w_sing = w[:-1] if w.endswith("s") and not w.endswith("ss") else w
                    if any(fw == w_sing or fw.rstrip("s") == w_sing for fw in fallback_words):
                        matched = True
                        break
            item_copy = dict(item)
            item_copy["amount"] = pantry_amt
            item_copy["unit"] = pantry_unit
            item_copy["suggested_amount"] = pantry_amt
            item_copy["used_amount_note"] = None
            if matched:
                item_copy["matched_recipe_ingredients"] = []
                likely_used.append(item_copy)
            else:
                other.append(item_copy)

    return likely_used, other


@bp.get("/recipe_menu")
def recipe_menu():
    if not session.get("user_id"):
        flash("Log in to view your recipes.", "info")
        return redirect(url_for("auth.login"))

    db = get_db()
    user_id = session["user_id"]

    pantry_items = list(db.receipt_items.find({"user_id": user_id}))
    pantry_by_id = {str(item["_id"]): item for item in pantry_items}
    pantry_names = {}
    for p in pantry_items:
        p_name = (p.get("item_name") or "").strip().lower()
        if p_name:
            pantry_names.setdefault(p_name, []).append(str(p["_id"]))

    items = list(
        db.recipes.find(
            {"user_id": user_id},
        ).sort("created_at", -1)
    )

    for item in items:
        recipe_updated = False
        ingredients = item.get("ingredients") or []
        for ing in ingredients:
            if isinstance(ing, dict):
                pid = ing.get("pantry_item_id")
                if pid and str(pid) in pantry_by_id:
                    if not ing.get("in_pantry"):
                        ing["in_pantry"] = True
                        recipe_updated = True
                elif pid and str(pid) not in pantry_by_id:
                    # Item was deleted from pantry
                    ing["in_pantry"] = False
                    ing["pantry_item_id"] = None
                    recipe_updated = True
                elif not pid:
                    # If ingredient was marked Need to buy, check if matching pantry item exists
                    ing_name = (ing.get("name") or ing.get("item") or "").strip()
                    cname = clean_ingredient_name(ing_name, ing.get("amount"), ing.get("unit")).strip().lower()
                    if cname in pantry_names:
                        matched_pid = pantry_names[cname][0]
                        ing["in_pantry"] = True
                        ing["pantry_item_id"] = matched_pid
                        recipe_updated = True

        if recipe_updated:
            db.recipes.update_one(
                {"_id": item["_id"], "user_id": user_id},
                {"$set": {"ingredients": ingredients}}
            )

    return render_template("recipe_menu.html", items=items)


@bp.route("/recipe_menu/<item_id>/complete", methods=("GET", "POST"))
def complete_recipe(item_id):
    if not session.get("user_id"):
        flash("Log in to update recipes.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        flash("That recipe does not exist.", "warning")
        return redirect(url_for("recipe_menu.recipe_menu"))

    recipe = get_db().recipes.find_one(
        {"_id": object_id, "user_id": session["user_id"]}
    )
    if not recipe:
        flash("That recipe does not exist.", "warning")
        return redirect(url_for("recipe_menu.recipe_menu"))

    pantry_items = list(
        get_db().receipt_items.find(
            {"user_id": session["user_id"]}
        ).sort("item_name", 1)
    )

    if request.method == "POST":
        action = request.form.get("action")
        if action == "skip":
            get_db().recipes.delete_one({"_id": object_id, "user_id": session["user_id"]})
            flash(f"'{recipe['recipe_name']}' marked as done.", "success")
            return redirect(url_for("recipe_menu.recipe_menu"))

        updated_count = 0
        deleted_count = 0

        for item in pantry_items:
            item_id_str = str(item["_id"])
            should_remove = request.form.get(f"remove_{item_id_str}") == "on"
            raw_amt = request.form.get(f"amount_{item_id_str}")
            if raw_amt is None:
                raw_amt = request.form.get(f"quantity_{item_id_str}")
            raw_unit = (request.form.get(f"unit_{item_id_str}") or "").strip()
            new_name = (request.form.get(f"item_name_{item_id_str}") or "").strip()

            is_zero_or_negative = False
            if raw_amt is not None and raw_amt.strip() != "":
                try:
                    val = float(raw_amt.strip())
                    if val <= 0:
                        is_zero_or_negative = True
                except (ValueError, TypeError):
                    pass

            if should_remove or is_zero_or_negative:
                get_db().receipt_items.delete_one(
                    {"_id": item["_id"], "user_id": session["user_id"]}
                )
                deleted_count += 1
            else:
                update_fields = {}
                if new_name and new_name != item.get("item_name"):
                    update_fields["item_name"] = new_name

                if raw_amt is not None and raw_amt.strip() != "":
                    std_amt, std_unit = standardize_unit_and_amount(raw_amt.strip(), raw_unit)
                    current_amt = item.get("amount") if item.get("amount") is not None else item.get("quantity")
                    current_unit = (item.get("unit") or "").strip()
                    if std_amt != current_amt:
                        update_fields["amount"] = std_amt
                        update_fields["quantity"] = std_amt
                    if std_unit != current_unit:
                        update_fields["unit"] = std_unit
                elif raw_amt is not None and raw_amt.strip() == "":
                    update_fields["amount"] = None
                    update_fields["quantity"] = None
                    update_fields["unit"] = "qty"

                if update_fields:
                    get_db().receipt_items.update_one(
                        {"_id": item["_id"], "user_id": session["user_id"]},
                        {"$set": update_fields}
                    )
                    updated_count += 1

        # Delete the recipe as completed
        get_db().recipes.delete_one({"_id": object_id, "user_id": session["user_id"]})

        msg_parts = [f"'{recipe['recipe_name']}' completed!"]
        if deleted_count > 0:
            msg_parts.append(f"{deleted_count} item(s) removed from pantry")
        if updated_count > 0:
            msg_parts.append(f"{updated_count} item(s) updated in pantry")
        flash(". ".join(msg_parts), "success")
        return redirect(url_for("recipe_menu.recipe_menu"))

    recipe_ingredients = recipe.get("ingredients") or []
    likely_used, other_items = find_matching_pantry_items(recipe_ingredients, pantry_items)

    return render_template(
        "complete_recipe.html",
        recipe=recipe,
        likely_used=likely_used,
        other_items=other_items,
        total_pantry_count=len(pantry_items),
    )


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
