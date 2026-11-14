# Durhack 2026

## Local setup

1. Create and activate a virtual environment:

   ```powershell
   py -m venv venv
   .\venv\Scripts\Activate.ps1
   ```
2. Install the dependencies:

   ```powershell
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set `SECRET_KEY`. Add your MongoDB Atlas
   connection string to `MONGO_URI` when database access is needed.
4. Start the development server:

   ```powershell
   flask run --debug
   ```
5. Create the initial MongoDB collections:

   ```powershell
   flask --app run init-db
   ```

The app uses the application factory in `app.create_app`. The factory creates
one reusable PyMongo `MongoClient` and stores the selected database in the
application extensions. MongoDB creates collections automatically when data is
first inserted, but the `app/migrations/` directory provides repeatable setup
for collections, indexes, and validators.

MongoDB does not use SQL-style migrations. Treat migration files as
idempotent database changes: add a new version when you need to create an
index, change validation rules, or migrate existing documents. Run them with
the `init-db` command after deploying. Applied versions are recorded in the
`_migrations` collection, so each migration runs once.

The example API endpoint is available at `/api/recipes`. Keep `MONGO_URI` in
`.env` only; never commit that file or expose its credentials.

The `v002_users` migration creates a `users` collection with required
`username`, `email`, and `password_hash` fields. Passwords must be hashed with
Werkzeug before insertion:

```python
from werkzeug.security import generate_password_hash

get_db().users.insert_one({
    "username": "alice",
    "email": "alice@example.com",
    "password_hash": generate_password_hash("a-password"),
})
```

The `v003_receipt_items` migration creates a `receipt_items` collection. Each
parsed item is linked to the logged-in user through `user_id` and grouped by a
`receipt_id`.

The browser authentication pages are available at:

- `/signup` to create an account
- `/login` to sign in
- `POST /logout` to sign out

Run the `v002_users` migration before using signup:

```powershell
flask --app run init-db
```

Receipt images can be uploaded at `/upload-receipt`. Accepted formats are
JPG, JPEG, PNG, and WebP, with a 10 MB limit. Files are saved in the operating
system temporary directory under `durhack2026-receipts`, processed with the OCR
pipeline in `app/image.py`, and deleted after processing. Tesseract OCR must
be installed separately and can be configured with the `TESSERACT_CMD`
environment variable when it is not on PATH.
