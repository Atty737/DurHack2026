import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from bson import ObjectId
from bson.errors import InvalidId
from werkzeug.utils import secure_filename

from app.db import get_db
from app.gemini_image import gemini_read_image, format_gemini_error
from google.genai import errors

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
        flash("Log in to upload a receipt.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        upload = request.files.get("receipt")

        if upload is None or not upload.filename:
            flash("Choose a receipt image to upload.", "warning")
        else:
            try:
                temporary_path = save_receipt_temporarily(upload)
            except ValueError as error:
                flash(str(error), "warning")
            else:
                try:
                    result = gemini_read_image(temporary_path)
                except FileNotFoundError:
                    flash("The uploaded receipt could not be read as an image.", "warning")
                except errors.APIError as error:
                    flash(format_gemini_error(error), "danger")
                except Exception as error:
                    flash(format_gemini_error(error), "danger")
                else:
                    receipt_id = uuid4().hex
                    items = [
                        {
                            "user_id": session["user_id"],
                            "receipt_id": receipt_id,
                            "item_name": item["item"],
                            "price": item.get("price"),
                            "amount": item.get("amount", item.get("quantity", 1)),
                            "unit": item.get("unit"),
                            "quantity": item.get("amount", item.get("quantity", 1)),
                            "created_at": datetime.now(timezone.utc),
                        }
                        for item in result
                    ]
                    if items:
                        get_db().receipt_items.insert_many(items)

                    flash(f"{len(items)} items uploaded and added to your pantry", "success")
                    return render_template(
                        "upload_receipt.html",
                        uploaded=True,
                        result=result,
                        saved_count=len(items),
                    )
                finally:
                    temporary_path.unlink(missing_ok=True)

    return render_template("upload_receipt.html", uploaded=False)


@bp.get("/receipt-items")
def receipt_items():
    if not session.get("user_id"):
        flash("Log in to view your receipt items.", "info")
        return redirect(url_for("auth.login"))

    items = list(
        get_db().receipt_items.find(
            {"user_id": session["user_id"]},
        ).sort("created_at", -1)
    )
    return render_template("pantry.html", items=items)


@bp.post("/receipt-items/<item_id>/delete")
def delete_receipt_item(item_id):
    if not session.get("user_id"):
        flash("Log in to delete receipt items.", "info")
        return redirect(url_for("auth.login"))

    try:
        object_id = ObjectId(item_id)
    except InvalidId:
        flash("That receipt item does not exist.", "warning")
        return redirect(url_for("receipts.receipt_items"))

    result = get_db().receipt_items.delete_one(
        {"_id": object_id, "user_id": session["user_id"]}
    )
    if result.deleted_count:
        flash("Receipt item deleted.", "success")
    else:
        flash("That receipt item does not exist.", "warning")

    return redirect(url_for("receipts.receipt_items"))


@bp.post("/receipt-items/delete-all")
def delete_all_receipt_items():
    if not session.get("user_id"):
        flash("Log in to delete receipt items.", "info")
        return redirect(url_for("auth.login"))

    result = get_db().receipt_items.delete_many(
        {"user_id": session["user_id"]}
    )
    flash(f"Deleted {result.deleted_count} item(s) from your pantry.", "success")
    return redirect(url_for("receipts.receipt_items"))
