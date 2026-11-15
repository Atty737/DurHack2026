from pymongo.database import Database
from pymongo.errors import CollectionInvalid, OperationFailure


def upgrade(db: Database):
    """Create the stores collection, backfill GeoJSON locations, and build a 2dsphere index."""
    try:
        db.create_collection("stores")
    except CollectionInvalid:
        pass

    # Backfill existing stores with GeoJSON Point format: [longitude, latitude]
    for store in db.stores.find():
        try:
            raw_lat = store.get("latitude")
            raw_lng = store.get("longitude")
            if raw_lat is not None and raw_lng is not None:
                lat = float(raw_lat)
                lng = float(raw_lng)
                db.stores.update_one(
                    {"_id": store["_id"]},
                    {
                        "$set": {
                            "location": {
                                "type": "Point",
                                "coordinates": [lng, lat],
                            },
                            "latitude": lat,
                            "longitude": lng,
                        }
                    },
                )
        except (ValueError, TypeError):
            continue

    # Create native 2dsphere index on location field for high-speed spatial queries
    try:
        db.stores.create_index([("location", "2dsphere")])
    except OperationFailure:
        pass

    # Apply schema validation
    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["name", "address"],
            "properties": {
                "name": {"bsonType": "string", "minLength": 1},
                "address": {"bsonType": "string"},
                "postcode": {"bsonType": ["string", "null"]},
                "latitude": {"bsonType": ["double", "int", "long", "decimal", "string", "null"]},
                "longitude": {"bsonType": ["double", "int", "long", "decimal", "string", "null"]},
                "location": {
                    "bsonType": ["object", "null"],
                    "required": ["type", "coordinates"],
                    "properties": {
                        "type": {"enum": ["Point"]},
                        "coordinates": {
                            "bsonType": "array",
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"bsonType": ["double", "int", "long", "decimal"]},
                        },
                    },
                },
            },
        }
    }

    try:
        db.command(
            "collMod",
            "stores",
            validator=validator,
            validationLevel="moderate",
        )
    except OperationFailure:
        pass
