from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from app.db import get_db


bp = Blueprint("auth", __name__)


@bp.route("/signup", methods=("GET", "POST"))
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Username, email, and password are required.")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.")
        elif password != confirm_password:
            flash("Passwords do not match.")
        else:
            try:
                user = {
                    "username": username,
                    "email": email,
                    "password_hash": generate_password_hash(password),
                }
                result = get_db().users.insert_one(user)
            except DuplicateKeyError:
                flash("That username or email is already registered.")
            else:
                session.clear()
                session["user_id"] = str(result.inserted_id)
                session["username"] = username
                return redirect(url_for("main.index"))

    return render_template("auth/signup.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().users.find_one({"username": username})

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.")
        else:
            session.clear()
            session["user_id"] = str(user["_id"])
            session["username"] = user["username"]
            return redirect(url_for("main.index"))

    return render_template("auth/login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))
