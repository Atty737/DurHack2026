from flask import Blueprint, render_template, jsonify, request, session, flash, redirect, url_for
from app.db import get_db

bp = Blueprint("nearest_shop", __name__)

@bp.get("/nearest_shop")
def nearest_shop():
    if not session.get("user_id"):
        flash("Log in to view recipes.", "info")
        return redirect(url_for("auth.login"))
    return render_template("nearest_shop.html")

@bp.route("/api/stores", methods=["GET"])
def get_stores():
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)

    stores = list(get_db().stores.find({}, {"_id":0, "name":1, "address":1, "postcode":1, "latitude":1, "longitude":1}))

    store_list = []
    for store in stores:
        store_data = store.copy()
        if user_lat and user_lng:
            store_data["distance"] = round(get_walking_route(user_lat, user_lng, store["latitude"], store["longitude"]), 1)
        else:
            store_data["distance"] = None
        store_list.append(store_data)

    print(store_list)

    if user_lat and user_lng:
        store_list.sort(key=lambda x: x["distance"])

    return jsonify(store_list)

import requests

def get_walking_route(user_lat, user_lng, store_lat, store_lng):
    url = f"http://router.project-osrm.org/route/v1/walking/{user_lng},{user_lat};{store_lng},{store_lat}?overview=false"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["routes"]:
            distance_meters = data["routes"][0]["distance"]
            distance_miles = distance_meters / 1609.34
            
            return distance_miles
            
    return None, None