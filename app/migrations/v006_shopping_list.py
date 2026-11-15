from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Create the collection used for shopping list items."""
    try:
        db.create_collection(
            "shopping_list",
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": [
                        "user_id",
                        "item_name",
                        "created_at",
                    ],
                    "properties": {
                        "user_id": {"bsonType": "string", "minLength": 1},
                        "item_name": {"bsonType": "string", "minLength": 1},
                        "raw_name": {
                            "bsonType": [
                                "string",
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
                        "recipe_id": {
                            "bsonType": [
                                "objectId",
                                "string",
                                "null",
                            ]
                        },
                        "recipe_name": {
                            "bsonType": [
                                "string",
                                "null",
                            ]
                        },
                        "checked": {
                            "bsonType": "bool",
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

    db.shopping_list.create_index("user_id")
    db.shopping_list.create_index([("user_id", 1), ("checked", 1)])
    db.shopping_list.create_index([("user_id", 1), ("recipe_id", 1)])
