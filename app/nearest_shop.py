import math
from flask import Blueprint, render_template, jsonify, request, session, flash, redirect, url_for
from app.db import get_db

bp = Blueprint("nearest_shop", __name__)


def haversine_miles(lat1, lon1, lat2, lon2):
    """Fallback distance calculation in miles using Haversine formula."""
    r = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 1)


@bp.get("/nearest_shop")
def nearest_shop():
    if not session.get("user_id"):
        flash("Log in to view recipes.", "info")
        return redirect(url_for("auth.login"))
    return render_template("nearest_shop.html")


@bp.get("/nearest_shop/add_permission")
def add_permission():
    if session.get("user_id") == "6af8c4b7a27e1eca91243f91":
        return jsonify({"permission": True})
    else:
        return jsonify({"permission": False})


@bp.route("/api/stores", methods=["GET"])
def get_stores():
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    db = get_db()

    # When user coordinates are provided, leverage MongoDB native geospatial $geoNear aggregation
    if user_lat is not None and user_lng is not None:
        try:
            pipeline = [
                {
                    "$geoNear": {
                        "near": {
                            "type": "Point",
                            "coordinates": [user_lng, user_lat],
                        },
                        "distanceField": "distance_meters",
                        "spherical": True,
                        "maxDistance": 50000,  # 50 km search radius
                    }
                },
                {
                    "$project": {
                        "_id": 0,
                        "name": 1,
                        "address": 1,
                        "postcode": 1,
                        "latitude": 1,
                        "longitude": 1,
                        "distance_meters": 1,
                        "distance": {
                            "$round": [
                                {"$divide": ["$distance_meters", 1609.34]},
                                1,
                            ]
                        },
                    }
                },
                {"$limit": 30},
            ]
            stores = list(db.stores.aggregate(pipeline))

            # Normalize numeric coordinates and ensure JSON serializable
            for s in stores:
                if "_id" in s:
                    s["id"] = str(s.pop("_id"))
                if s.get("latitude") is not None:
                    s["latitude"] = float(s["latitude"])
                if s.get("longitude") is not None:
                    s["longitude"] = float(s["longitude"])

            return jsonify(stores)
        except Exception:
            # Fallback to in-memory spatial sorting if running in an environment without 2dsphere index
            raw_stores = list(db.stores.find({}, {"_id": 0, "name": 1, "address": 1, "postcode": 1, "latitude": 1, "longitude": 1, "location": 1}))
            store_list = []
            for s in raw_stores:
                if "_id" in s:
                    s.pop("_id", None)
                lat = float(s["latitude"]) if s.get("latitude") is not None else None
                lng = float(s["longitude"]) if s.get("longitude") is not None else None
                if lat is not None and lng is not None:
                    s["latitude"] = lat
                    s["longitude"] = lng
                    s["distance"] = haversine_miles(user_lat, user_lng, lat, lng)
                    store_list.append(s)
            store_list.sort(key=lambda x: x.get("distance", float("inf")))
            return jsonify(store_list[:30])

    # If coordinates are omitted, return stores without distance
    raw_stores = list(db.stores.find({}, {"_id": 0, "name": 1, "address": 1, "postcode": 1, "latitude": 1, "longitude": 1}).limit(50))
    for s in raw_stores:
        if "_id" in s:
            s.pop("_id", None)
        if s.get("latitude") is not None:
            s["latitude"] = float(s["latitude"])
        if s.get("longitude") is not None:
            s["longitude"] = float(s["longitude"])
        s["distance"] = None

    return jsonify(raw_stores)


@bp.route("/addStore")
def addStore():
    raw_lat = request.args.get("latitude")
    raw_lng = request.args.get("longitude")
    name = request.args.get("shopName")
    address = request.args.get("address")
    postcode = request.args.get("postcode")

    try:
        lat = float(raw_lat)
        lng = float(raw_lng)
        entry = {
            "name": name,
            "address": address,
            "postcode": postcode,
            "latitude": lat,
            "longitude": lng,
            "location": {
                "type": "Point",
                "coordinates": [lng, lat],  # GeoJSON specification: [longitude, latitude]
            },
        }
    except (ValueError, TypeError):
        entry = {
            "name": name,
            "address": address,
            "postcode": postcode,
            "latitude": raw_lat,
            "longitude": raw_lng,
        }

    get_db().stores.insert_one(entry)
    return jsonify({"success": True})
