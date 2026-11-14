from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Add quantity field to receipt_items collection schema and backfill existing documents."""
    try:
        db.create_collection("receipt_items")
    except CollectionInvalid:
        pass

    # Ensure all existing items have a default quantity of 1
    db.receipt_items.update_many(
        {"quantity": {"$exists": False}},
        {"$set": {"quantity": 1}},
    )

    validator = {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "user_id",
                "receipt_id",
                "item_name",
                "price",
                "quantity",
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
