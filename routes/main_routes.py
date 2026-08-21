# routes/main_routes.py
#
# The dashboard and research-project screens. Every route here needs the user to be
# logged in - that's what the login_required decorator below enforces: it checks for
# session["user_id"] before running the actual view function, and bounces the visitor
# to the login page if it's missing.

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

from services.database_service import get_session
from services.project_service import create_project, get_projects_for_user, get_project_for_user

main_bp = Blueprint("main", __name__)


def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)
    return wrapped_view


@main_bp.route("/")
@login_required
def dashboard():
    user_id = session["user_id"]
    db_session = get_session()
    try:
        projects = get_projects_for_user(db_session, user_id)
    finally:
        db_session.close()

    stats = [
        ("Research Projects", len(projects)),
        ("Saved Papers", 0),
        ("Papers Analysed", 0),
        ("Potential Gaps Found", 0),
    ]
    return render_template("dashboard.html", projects=projects, stats=stats)


@main_bp.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    db_session = get_session()
    try:
        project = get_project_for_user(db_session, session["user_id"], project_id)
    finally:
        db_session.close()

    if project is None:
        # Either this project doesn't exist, or it belongs to someone else - either
        # way, show a plain "not found" rather than leaking which case it is.
        abort(404)

    return render_template("project_detail.html", project=project)


@main_bp.route("/projects/new", methods=["GET", "POST"])
@login_required
def new_project():
    if request.method == "GET":
        return render_template("new_project.html", errors={}, form={})

    title = request.form.get("title", "").strip()
    research_question = request.form.get("research_question", "").strip()
    research_field = request.form.get("research_field", "").strip()
    keywords = request.form.get("keywords", "").strip()

    errors = {}
    if not title:
        errors["title"] = "Please give your project a title."

    if errors:
        return render_template(
            "new_project.html",
            errors=errors,
            form={
                "title": title,
                "research_question": research_question,
                "research_field": research_field,
                "keywords": keywords,
            },
        )

    db_session = get_session()
    try:
        create_project(
            db_session,
            user_id=session["user_id"],
            title=title,
            research_question=research_question,
            research_field=research_field,
            keywords=keywords,
        )
    finally:
        db_session.close()

    flash("Research project created.", "success")
    return redirect(url_for("main.dashboard"))