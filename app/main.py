from flask import Blueprint, render_template, session, jsonify


bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    return render_template("index.html")

@bp.get("/loggedin")
def logged_in():
    if not session.get("user_id"):
        return jsonify({"logged_in":False})
    return jsonify({"logged_in":True})