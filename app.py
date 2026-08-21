# app.py
#
# The entry point for the whole app. Run it with:
#     python app.py
#
# Flask uses a SECRET_KEY to cryptographically sign the login session cookie, so users
# can't tamper with it. We read it from an environment variable (see .env.example) and
# fall back to a placeholder for local development - swap in a real random value in
# .env before this ever leaves your laptop.

import os
from flask import Flask, session
from dotenv import load_dotenv

from services.database_service import init_db, get_session
from models.user import User
from routes.auth_routes import auth_bp
from routes.main_routes import main_bp

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-this")

init_db()  # creates database/researchlens.db and its tables the first time this runs

app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)


@app.context_processor
def inject_current_user():
    """
    Makes a `current_user` variable available inside every template automatically,
    so base_app.html can show the signed-in user's name without every route having
    to pass it in manually.
    """
    user_id = session.get("user_id")
    if not user_id:
        return {"current_user": None}

    db_session = get_session()
    try:
        user = db_session.query(User).get(user_id)
    finally:
        db_session.close()
    return {"current_user": user}


if __name__ == "__main__":
    app.run(debug=True)
