from flask import Blueprint, render_template, jsonify, request
import math

bp = Blueprint("nearest_shop", __name__)

STORES = []

@bp.get("/nearest_shop")
def nearest_shop():
    return render_template("nearest_shop.html")

@bp.route("/api/stores", methods=["GET"])
def get_stores():
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)

    store_list = []
    for store in STORES:
        store_data = store.copy()
        if user_lat and user_lng:
            store_data["distance"] = round(get_walking_route(user_lat, user_lng, store["lat"], store["lng"]))
        else:
            store_data["distance"] = None
        store_list.append(store_data)

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
            
            return round(distance_miles, 2)
            
    return None, None