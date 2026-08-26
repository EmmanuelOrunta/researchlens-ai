# routes/settings_routes.py
#
# The Settings page - changing your display name and changing your password. These
# are two separate forms (and two separate POST routes), each submitting only its own
# fields - that way a mistake in the password form doesn't wipe out what you'd typed
# in the name field, and each gets its own focused success/error message.

from flask import Blueprint, render_template, request, redirect, url_for, session, flash

from services.database_service import get_session
from services.auth_service import (
    get_user_by_id,
    verify_password,
    update_user_name,
    update_user_password,
)
from routes.main_routes import login_required
from routes.auth_routes import get_password_error

settings_bp = Blueprint("settings", __name__)


@settings_bp.route("/settings")
@login_required
def settings():
    db_session = get_session()
    try:
        user = get_user_by_id(db_session, session["user_id"])
    finally:
        db_session.close()

    return render_template("settings.html", user=user, name_errors={}, password_errors={}, name_form={})


@settings_bp.route("/settings/profile", methods=["POST"])
@login_required
def update_profile():
    name = request.form.get("name", "").strip()

    errors = {}
    if not name:
        errors["name"] = "Please enter your name."

    db_session = get_session()
    try:
        user = get_user_by_id(db_session, session["user_id"])

        if errors:
            return render_template(
                "settings.html", user=user,
                name_errors=errors, password_errors={}, name_form={"name": name},
            )

        update_user_name(db_session, user, name)
    finally:
        db_session.close()

    flash("Your name has been updated.", "success")
    return redirect(url_for("settings.settings"))


@settings_bp.route("/settings/password", methods=["POST"])
@login_required
def update_password():
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_new_password = request.form.get("confirm_new_password", "")

    db_session = get_session()
    try:
        user = get_user_by_id(db_session, session["user_id"])

        errors = {}
        if not current_password or not verify_password(current_password, user.password_hash):
            errors["current_password"] = "That's not your current password."

        if not new_password:
            errors["new_password"] = "Please choose a new password."
        else:
            password_error = get_password_error(new_password)
            if password_error:
                errors["new_password"] = password_error

        if not confirm_new_password:
            errors["confirm_new_password"] = "Please confirm your new password."
        elif new_password and new_password != confirm_new_password:
            errors["confirm_new_password"] = "Passwords do not match."

        if errors:
            return render_template(
                "settings.html", user=user,
                name_errors={}, password_errors=errors, name_form={},
            )

        update_user_password(db_session, user, new_password)
    finally:
        db_session.close()

    flash("Your password has been updated.", "success")
    return redirect(url_for("settings.settings"))
