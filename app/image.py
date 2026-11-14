import os
import re
import statistics

import cv2
import pytesseract
from pytesseract import Output

if tesseract_cmd := os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

AUTO_FIND_SCALE = True
DEFAULT_SCALE = 2.5
TESS_CONFIG = r"--psm 6"


def reconstruct_lines_by_y(words):
    """
    Groups detected words into rows based on vertical Y-center proximity rather than
    Tesseract's line_num, so wrinkled/tilted receipts keep left items aligned with right prices.
    """
    if not words:
        return ""

    sorted_words = sorted(words, key=lambda w: w["box"][1] + w["box"][3] / 2.0)
    rows = []

    for w in sorted_words:
        x, y, bw, bh = w["box"]
        cy = y + bh / 2.0
        placed = False

        for row in rows:
            row_cy = sum(item["cy"] for item in row) / len(row)
            row_h = sum(item["box"][3] for item in row) / len(row)
            tolerance = max(bh, row_h) * 0.55

            if abs(cy - row_cy) <= tolerance:
                row.append({**w, "cy": cy})
                placed = True
                break

        if not placed:
            rows.append([{**w, "cy": cy}])

    reconstructed = []
    for row in rows:
        row.sort(key=lambda item: item["box"][0])
        reconstructed.append(" ".join(item["text"] for item in row))

    return "\n".join(reconstructed)


def scan_image(img, scale=1.0):
    """Runs Tesseract and returns structured words, Y-aligned lines, and stats."""
    data = pytesseract.image_to_data(
        img,
        lang="eng",
        config=TESS_CONFIG,
        output_type=Output.DICT
    )

    words = []
    box_heights = []

    for i, raw_word in enumerate(data["text"]):
        word = raw_word.strip()
        if not word:
            continue

        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            continue

        if conf < 0:
            continue

        x = int(data["left"][i] / scale)
        y = int(data["top"][i] / scale)
        w = int(data["width"][i] / scale)
        h = int(data["height"][i] / scale)

        words.append({"text": word, "conf": conf, "box": (x, y, w, h)})
        box_heights.append(h)

    avg_conf = sum(w["conf"] for w in words) / len(words) if words else 0.0
    median_height = statistics.median(box_heights) if box_heights else 0.0
    reconstructed_text = reconstruct_lines_by_y(words)

    return {
        "words": words,
        "text": reconstructed_text,
        "word_count": len(words),
        "avg_conf": avg_conf,
        "median_height": median_height
    }


def make_clean_gray(bgr_img, scale):
    """Pipeline A (Best for crisp/simple screenshots): Upscale + Grayscale only."""
    resized = cv2.resize(bgr_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) if scale != 1.0 else bgr_img
    return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)


def make_shadow_cleaned(bgr_img, scale):
    """Pipeline B (Best for camera photos with folds/bleed-through): Shadow division + Otsu."""
    gray = make_clean_gray(bgr_img, scale)
    bg_kernel = max(51, int(round(35 * scale)) | 1)
    bg = cv2.GaussianBlur(gray, (bg_kernel, bg_kernel), 0)
    normalized = cv2.divide(gray, bg, scale=255)
    _, binary = cv2.threshold(normalized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def score_scan(scan_result):
    """Scores scan quality by rewarding both confidence and valid price/word detections."""
    if scan_result["word_count"] == 0:
        return 0.0
    price_hits = sum(1 for w in scan_result["words"] if re.search(r"\d+[.,]\d{2}", w["text"]))
    return scan_result["avg_conf"] + (scan_result["word_count"] * 0.2) + (price_hits * 1.5)


def find_best_pipeline_and_scale(bgr_img, baseline_scan):
    """Tests both Clean Grayscale and Shadow-Normalized Otsu across candidate scales."""
    est_scale = DEFAULT_SCALE
    if baseline_scan["median_height"] > 0:
        raw_est = 32.0 / baseline_scan["median_height"]
        est_scale = round(min(max(raw_est, 1.0), 3.5), 1)

    candidates = sorted(set([1.0, 1.5, 2.0, 2.5, 3.0, 3.2, est_scale]))
    max_allowed_scale = 4000.0 / bgr_img.shape[1]
    candidates = [s for s in candidates if s <= max_allowed_scale] or [1.0]

    best_mode = "Raw Original"
    best_scale = 1.0
    best_scan = baseline_scan
    best_ocr_img = None
    best_score = score_scan(baseline_scan)
    trial_log = []

    pipelines = [
        ("Clean Grayscale", make_clean_gray),
        ("Shadow-Cleaned Otsu", make_shadow_cleaned),
    ]

    for mode_name, fn in pipelines:
        for s in candidates:
            ocr_img = fn(bgr_img, s)
            result = scan_image(ocr_img, scale=s)
            sc = score_scan(result)
            trial_log.append((mode_name, s, result["word_count"], result["avg_conf"], sc))

            if sc > best_score:
                best_score = sc
                best_mode = mode_name
                best_scale = s
                best_scan = result
                best_ocr_img = ocr_img

    return best_mode, best_scale, best_scan, best_ocr_img, est_scale, trial_log


def extract_end_price(line):
    """Extracts a price (including negative discounts like -£1.50 or circled £5.00) from the end of a row."""
    match = re.search(
        r"(?P<sign>-)?\s*[£$€S(]?\s*(?P<num>\d+[.,]\s*\d{2})\s*[)O0A-Za-z]?$",
        line
    )
    if not match:
        return line, None

    item_part = line[:match.start()]
    num_str = match.group("num").replace(" ", "").replace(",", ".")
    try:
        val = float(num_str)
        if match.group("sign"):
            val = -val
        return item_part, val
    except ValueError:
        return line, None


def sanitize_letters_only(text):
    """
    Removes all numbers, symbols, and weird characters, keeping only A-Z letters and single spaces.
    Also removes isolated 1-letter OCR noise (e.g. stray 'l' or 'X') unless it's 'a'.
    """
    letters_only = re.sub(r"[^a-zA-Z\s]", " ", text)
    tokens = [
        tok for tok in letters_only.split()
        if len(tok) >= 2 or tok.lower() == "a"
    ]
    return " ".join(tokens)


def parse_items_to_2d_array(text):
    """Parses Y-aligned receipt rows into [[letters_only_item, price], ...]."""
    items_2d = []

    ignore_keywords = (
        "tesco", "extra", "express", "metro", "any questions", "www",
        "store locator", "vat number", "vat reg", "thank you", "subtotal",
        "sub total", "total", "tax", "vat", "cash", "change", "visa",
        "mastercard", "debit", "credit", "card", "balance", "due",
        "amount", "tender", "savings", "welcome", "receipt", "invoice",
        "tel", "phone", "http", "store", "branch", "cashier", "operator",
        "served by", "date", "time", "auth code", "aid", "merchant",
        "customer copy", "keep your receipt", "road", "street", "high st"
    )

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        raw_item_part, price = extract_end_price(line)
        clean_item = sanitize_letters_only(raw_item_part)

        # Require at least one real word of 3+ letters to filter out stray OCR/bleed-through noise
        if not re.search(r"[a-zA-Z]{3,}", clean_item):
            continue

        lower = clean_item.lower()
        if any(k in lower for k in ignore_keywords):
            continue

        if price is not None:
            if lower.startswith("cc") or lower.startswith("ce") or price < 0:
                items_2d.append(["Clubcard Discount", price])
            else:
                items_2d.append([clean_item, price])
        else:
            # Attach continuation lines (e.g. "Pints", "Croissants Pack", "Price Marked")
            if items_2d and items_2d[-1][0] != "Clubcard Discount":
                items_2d[-1][0] = f"{items_2d[-1][0]} {clean_item}".strip()
            else:
                items_2d.append([clean_item, None])

    return items_2d


def process_receipt(image_path):
    """Run OCR on an uploaded receipt and return parsed items and metadata."""
    image = cv2.imread(str(image_path))
    if image is None:
        raise FileNotFoundError(f"Unable to load image: {image_path}")

    raw_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    baseline = scan_image(raw_rgb, scale=1.0)
    best_mode, chosen_scale, final_scan, _, est_scale, trial_log = (
        find_best_pipeline_and_scale(image, baseline)
    )
    items_2d = parse_items_to_2d_array(final_scan["text"])

    return {
        "items": items_2d,
        "text": final_scan["text"],
        "avg_conf": final_scan["avg_conf"],
        "best_mode": best_mode,
        "chosen_scale": chosen_scale,
        "estimated_scale": est_scale,
        "trial_log": trial_log,
    }

