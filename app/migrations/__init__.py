from pymongo.database import Database

from app.migrations.v001_initial import upgrade as initial_upgrade
from app.migrations.v002_users import upgrade as users_upgrade
from app.migrations.v003_receipt_items import upgrade as receipt_items_upgrade
from app.migrations.v004_receipt_items_quantity import upgrade as receipt_items_quantity_upgrade
from app.migrations.v005_receipt_items_amount_unit import upgrade as receipt_items_amount_unit_upgrade


MIGRATIONS = (
    ("v001_initial", initial_upgrade),
    ("v002_users", users_upgrade),
    ("v003_receipt_items", receipt_items_upgrade),
    ("v004_receipt_items_quantity", receipt_items_quantity_upgrade),
    ("v005_receipt_items_amount_unit", receipt_items_amount_unit_upgrade),
)


def run(db: Database):
    migrations = db["_migrations"]
    migrations.create_index("version", unique=True)
    applied = {
        migration["version"]
        for migration in migrations.find({}, {"_id": 0, "version": 1})
    }

    for version, upgrade in MIGRATIONS:
        if version in applied:
            continue

        upgrade(db)
        migrations.insert_one({"version": version})
