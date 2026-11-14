import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
import pytesseract
from werkzeug.utils import secure_filename

from app.db import get_db
from app.image import process_receipt

bp = Blueprint("receipts", __name__)

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_RECEIPT_SIZE = 10 * 1024 * 1024


def save_receipt_temporarily(upload):
    filename = secure_filename(upload.filename or "")
    extension = Path(filename).suffix.lower().lstrip(".")

    if not filename or extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Please upload a JPG, JPEG, PNG, or WebP image.")

    temporary_directory = Path(tempfile.gettempdir()) / "durhack2026-receipts"
    temporary_directory.mkdir(exist_ok=True)
    temporary_path = temporary_directory / f"{uuid4().hex}.{extension}"
    upload.save(temporary_path)
    return temporary_path


@bp.route("/upload-receipt", methods=("GET", "POST"))
def upload_receipt():
    if not session.get("user_id"):
        flash("Log in to upload a receipt.")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        upload = request.files.get("receipt")

        if upload is None or not upload.filename:
            flash("Choose a receipt image to upload.")
        else:
            try:
                temporary_path = save_receipt_temporarily(upload)
            except ValueError as error:
                flash(str(error))
            else:
                try:
                    result = process_receipt(temporary_path)
                except pytesseract.TesseractNotFoundError:
                    flash(
                        "Receipt processing is unavailable because Tesseract "
                        "OCR is not installed or configured."
                    )
                except FileNotFoundError:
                    flash("The uploaded receipt could not be read as an image.")
                else:
                    receipt_id = uuid4().hex
                    items = [
                        {
                            "user_id": session["user_id"],
                            "receipt_id": receipt_id,
                            "item_name": item,
                            "price": price,
                            "created_at": datetime.now(timezone.utc),
                        }
                        for item, price in result["items"]
                    ]
                    if items:
                        get_db().receipt_items.insert_many(items)

                    flash("Receipt uploaded and processed.")
                    return render_template(
                        "upload_receipt.html",
                        uploaded=True,
                        result=result,
                        saved_count=len(items),
                    )
                finally:
                    temporary_path.unlink(missing_ok=True)

    return render_template("upload_receipt.html", uploaded=False)
