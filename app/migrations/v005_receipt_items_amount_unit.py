from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Add amount and unit fields to receipt_items collection schema and backfill existing documents."""
    try:
        db.create_collection("receipt_items")
    except CollectionInvalid:
        pass

    # Backfill amount and unit from quantity if amount is missing
    for doc in db.receipt_items.find({"amount": {"$exists": False}}):
        amt = doc.get("quantity") if doc.get("quantity") is not None else 1
        db.receipt_items.update_one(
            {"_id": doc["_id"]},
            {"$set": {"amount": amt, "unit": doc.get("unit", None)}}
        )

    # Ensure any remaining documents have unit set (nullable)
    db.receipt_items.update_many(
        {"unit": {"$exists": False}},
        {"$set": {"unit": None}}
    )

    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "user_id",
                "receipt_id",
                "item_name",
                "price",
                "amount",
                "created_at",
            ],
            "properties": {
                "user_id": {"bsonType": "string", "minLength": 1},
                "receipt_id": {"bsonType": "string", "minLength": 1},
                "item_name": {"bsonType": "string", "minLength": 1},
                "price": {
                    "bsonType": [
                        "double",
                        "int",
                        "long",
                        "decimal",
                        "null",
                    ]
                },
                "amount": {
                    "bsonType": [
                        "int",
                        "long",
                        "double",
                        "decimal",
                        "null",
                    ]
                },
                "unit": {
                    "bsonType": [
                        "string",
                        "null",
                    ]
                },
                "quantity": {
                    "bsonType": [
                        "int",
                        "long",
                        "double",
                        "decimal",
                        "null",
                    ]
                },
                "created_at": {"bsonType": "date"},
            },
        }
    }

    db.command(
        "collMod",
        "receipt_items",
        validator=validator,
        validationLevel="strict",
        validationAction="error",
    )
