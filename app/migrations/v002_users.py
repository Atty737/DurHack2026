from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Create the users collection and enforce unique login fields."""
    try:
        db.create_collection(
            "users",
            validator={
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["username", "password_hash", "email"],
                    "properties": {
                        "username": {"bsonType": "string", "minLength": 1},
                        "password_hash": {"bsonType": "string", "minLength": 1},
                        "email": {"bsonType": "string", "minLength": 3},
                    },
                }
            },
            validationLevel="strict",
            validationAction="error",
        )
    except CollectionInvalid:
        pass

    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
