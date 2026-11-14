from pymongo.database import Database
from pymongo.errors import CollectionInvalid


def upgrade(db: Database):
    """Create the application's initial collections.

    MongoDB creates collections automatically on the first insert. Keeping
    this operation explicit makes local setup and deployments repeatable.
    """
    for collection_name in ("recipes"):
        try:
            db.create_collection(collection_name)
        except CollectionInvalid:
            pass
