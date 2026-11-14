# Durhack 2026

## Local setup

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and set `SECRET_KEY`. Add your MongoDB Atlas
   connection string to `MONGO_URI` when database access is needed.

4. Start the development server:

   ```powershell
   flask --app run run --debug
   ```

The app uses the application factory in `app.create_app`. MongoDB is optional
for the initial web page: when `MONGO_URI` is unset, the app starts without a
database connection. When it is set, the configured `MongoClient` and database
are available through `app.extensions["mongo_client"]` and
`app.extensions["mongo_db"]`.
