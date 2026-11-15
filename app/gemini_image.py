from google import genai
from google.genai import errors
from dotenv import load_dotenv
import json
import re


def format_gemini_error(err: Exception) -> str:
    """Extract a user-friendly flash error message from Gemini API errors."""
    msg = getattr(err, "message", None)
    code = getattr(err, "code", None)

    if msg:
        if code:
            return f"Gemini error ({code}): {msg}"
        return f"Gemini error: {msg}"

    details = getattr(err, "details", None)
    if isinstance(details, dict):
        error_info = details.get("error", details)
        if isinstance(error_info, dict) and error_info.get("message"):
            err_msg = error_info["message"]
            err_code = error_info.get("code") or code
            return f"Gemini error ({err_code}): {err_msg}" if err_code else f"Gemini error: {err_msg}"

    err_str = str(err)
    if "503" in err_str or "UNAVAILABLE" in err_str:
        return "Gemini is currently experiencing high demand (503 Unavailable). Please try again shortly."
    return f"Gemini error: {err_str}"


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


def clean_ingredient_name(name: str, amount=None, unit=None) -> str:
    """Extract clean food item name by stripping leading amounts and numbers."""
    if not name or not isinstance(name, str):
        return ""
    cleaned = name.strip()
    pattern = r"^(?:[\d\.\/]+)\s*(?:(?:g|kg|ml|ltr|litres?|grams?|oz|lbs?|tbsp|tsp|cups?|pinches?|tins?|cans?|qty|pieces?|x)\b)?\s*(?:of\s+)?"
    res = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
    if res and len(res) > 1:
        return res[0].upper() + res[1:]
    return cleaned


def standardize_unit_and_amount(amount, unit):
    """Normalize units to standard 'g', 'ml', or 'qty' and convert amounts accordingly."""
    if amount is None:
        return 1, "qty"

    try:
        raw_str = str(amount).strip()
        num = float(raw_str) if "." in raw_str else int(raw_str)
    except (ValueError, TypeError):
        num = 1

    u = (unit or "").lower().strip()

    # Weight -> grams ('g')
    if u in ("g", "gram", "grams"):
        return num, "g"
    elif u in ("kg", "kilo", "kilos", "kilogram", "kilograms"):
        val = round(num * 1000.0, 2)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "g"
    elif u in ("mg", "milligram", "milligrams"):
        val = round(num / 1000.0, 3)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "g"
    elif u in ("lb", "lbs", "pound", "pounds"):
        val = round(num * 453.592, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "g"
    elif u in ("oz", "ounce", "ounces"):
        val = round(num * 28.3495, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "g"

    # Volume / Liquid -> millilitres ('ml')
    elif u in ("ml", "millilitre", "millilitres", "milliliter", "milliliters"):
        return num, "ml"
    elif u in ("l", "liter", "liters", "litre", "litres"):
        val = round(num * 1000.0, 2)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"
    elif u in ("cl", "centilitre", "centilitres", "centiliter", "centiliters"):
        val = round(num * 10.0, 2)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"
    elif u in ("pint", "pints", "pt"):
        # UK pint is ~568ml
        val = round(num * 568.0, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"
    elif u in ("cup", "cups"):
        val = round(num * 240.0, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"
    elif u in ("tbsp", "tablespoon", "tablespoons"):
        val = round(num * 15.0, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"
    elif u in ("tsp", "teaspoon", "teaspoons"):
        val = round(num * 5.0, 1)
        return int(val) if isinstance(val, float) and val.is_integer() else val, "ml"

    # Count / pieces -> 'qty'
    else:
        return num, "qty"


def gemini_read_image(image_path):
    load_dotenv()
    client = genai.Client()

    file = client.files.upload(file=image_path)

    prompt = (
        "Return a valid JSON array of objects in the format: "
        "[{\"item\": \"<generic_item_name>\", \"amount\": <numeric_amount>, \"unit\": \"<standard_unit>\", \"price\": <item_price>}].\n"
        "Rules:\n"
        "1. Only include food and beverage items; ignore non-food items (carrier bags, toiletries, cleaners), discounts, savings, coupons, and totals.\n"
        "2. Convert all item names to generic, clean food names. Remove supermarket brand names (e.g. Tesco, Sainsbury's, Asda, Morrisons, Aldi, Lidl, Marks & Spencer, Waitrose, Essential), manufacturer brands (e.g. Heinz, Warburtons, Lurpak), and filler words like 'Each', 'Loose', 'Twin Pack', 'Class 1', 'Produce Of', and packaging barcodes (e.g. rather than 'Tesco Whole Cucumber Each', use 'Cucumber'; rather than 'Sainsbury's British Whole Milk 4 Pints', use 'Whole Milk'; rather than 'Warburtons Medium White Bread 800g', use 'White Bread').\n"
        "3. ALWAYS use standard units for 'unit' and convert if not:\n"
        "   - Use 'g' for weight/mass (always convert kg to g, e.g. 1kg -> amount: 1000, unit: 'g'; 500g -> amount: 500, unit: 'g').\n"
        "   - Use 'ml' for volume/liquids (always convert litres, pints, cups to ml, e.g. 1L -> amount: 1000, unit: 'ml'; 4 pints -> amount: 2272, unit: 'ml'; 2 pints -> amount: 1136, unit: 'ml'; 1 pint -> amount: 568, unit: 'ml'; 250ml -> amount: 250, unit: 'ml').\n"
        "   - Use 'qty' for countable items / pieces (e.g. 2 cucumbers -> amount: 2, unit: 'qty'; 6 eggs -> amount: 6, unit: 'qty'; 1 loaf -> amount: 1, unit: 'qty'; 1 tin -> amount: 1, unit: 'qty').\n"
        "   The 'unit' field MUST strictly be one of: 'g', 'ml', or 'qty'.\n"
        "4. Capitalise the first letter of each word (Title Case) for item name, and expand any shortened or abbreviated receipt jargon into full words (e.g. 'Whl Cuke' -> 'Cucumber', 'Org Lemons' -> 'Lemons', 'Chkn Brst' -> 'Chicken Breast', 'Potts' -> 'Potatoes').\n"
        "5. Output ONLY the raw JSON array with no markdown fences, backticks, or extra text."
    )

    interaction = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=[
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "uri": file.uri,
                "mime_type": file.mime_type
            }
        ]
    )

    output_text = getattr(interaction, "output_text", None) or getattr(interaction, "text", "")
    items = json.loads(clean_json_text(output_text))

    for item in items:
        if isinstance(item.get("price"), (int, float)):
            item["price"] = round(float(item["price"]), 2)

        # Parse and standardize amount and unit
        raw_amt = item.get("amount") if item.get("amount") is not None else item.get("quantity")
        raw_unit = item.get("unit")
        std_amt, std_unit = standardize_unit_and_amount(raw_amt, raw_unit)

        item["amount"] = std_amt
        item["unit"] = std_unit
        item["quantity"] = std_amt

    return items
