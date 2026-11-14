from flask import Blueprint, render_template


bp = Blueprint("prices", __name__)

@bp.route("/api/price/<product_id>")
def prices():
    return render_template("prices.html")