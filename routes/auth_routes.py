# routes/auth_routes.py
#
# Everything to do with registering, logging in, and logging out.
#
# Each route follows the same shape: on a GET request, just show the empty form.
# On a POST request (the form was submitted), validate the input field-by-field,
# building up an `errors` dict of {field_name: message}. If there are any errors,
# re-render the same page with those messages next to the relevant fields (this is
# what draws the red inline error text you see under a field). If everything is valid,
# do the actual work (create the account / log the user in) and redirect to the dashboard.

import re
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from services.database_service import get_session
from services.auth_service import hash_password, verify_password, get_user_by_email, create_user

auth_bp = Blueprint("auth", __name__)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Sprint 1 password rule: at least 8 characters, with an uppercase letter, a lowercase
# letter, a number, and a special character. Used only at registration - login just
# checks the password matches, it doesn't re-validate its shape.
PASSWORD_MIN_LENGTH = 8


def get_password_error(password: str):
    """Return an error message if the password doesn't meet the complexity rules, else None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters long."
    if not re.search(r"[A-Z]", password):
        return "Password must include at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return "Password must include at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must include at least one number."
    if not re.search(r"[^A-Za-z0-9]", password):
        return "Password must include at least one special character (e.g. ! @ # $ %)."
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", errors={}, form={})

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    errors = {}
    if not email:
        errors["email"] = "Please enter your email."
    elif not EMAIL_PATTERN.match(email):
        errors["email"] = "Please enter a valid email address."

    if not password:
        errors["password"] = "Please enter your password."

    if not errors:
        db_session = get_session()
        try:
            user = get_user_by_email(db_session, email)
            if not user or not verify_password(password, user.password_hash):
                errors["password"] = "Incorrect email or password."
            else:
                session["user_id"] = user.id
        finally:
            db_session.close()

    if errors:
        return render_template("login.html", errors=errors, form={"email": email})

    return redirect(url_for("main.dashboard"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", errors={}, form={})

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    errors = {}
    if not name:
        errors["name"] = "Please enter your full name."
    if not email:
        errors["email"] = "Please enter your email."
    elif not EMAIL_PATTERN.match(email):
        errors["email"] = "Please enter a valid email address."
    if not password:
        errors["password"] = "Please choose a password."
    else:
        password_error = get_password_error(password)
        if password_error:
            errors["password"] = password_error
    if not confirm_password:
        errors["confirm_password"] = "The confirm password field is required."
    elif password and password != confirm_password:
        errors["confirm_password"] = "Passwords do not match."

    db_session = get_session()
    try:
        if "email" not in errors and get_user_by_email(db_session, email):
            errors["email"] = "An account with this email already exists."

        if errors:
            return render_template("register.html", errors=errors, form={"name": name, "email": email})

        user = create_user(db_session, name=name, email=email, password_hash=hash_password(password))
        session["user_id"] = user.id
    finally:
        db_session.close()

    return redirect(url_for("main.dashboard"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You've been logged out.", "success")
    return redirect(url_for("auth.login"))
