from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Create the collection used for parsed receipt items."""
    try:
        db.create_collection(
            "receipt_items",
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": [
                        "user_id",
                        "receipt_id",
                        "item_name",
                        "price",
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
                        "created_at": {"bsonType": "date"},
                    },
                }
            },
            validationLevel="strict",
            validationAction="error",
        )
    except CollectionInvalid:
        pass

    db.receipt_items.create_index("user_id")
    db.receipt_items.create_index([("user_id", 1), ("receipt_id", 1)])
