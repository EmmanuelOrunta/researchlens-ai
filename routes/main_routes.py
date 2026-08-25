# routes/main_routes.py
#
# The dashboard and research-project screens. Every route here needs the user to be
# logged in - that's what the login_required decorator below enforces: it checks for
# session["user_id"] before running the actual view function, and bounces the visitor
# to the login page if it's missing.

from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, abort

from services.database_service import get_session
from services.project_service import (
    create_project,
    get_projects_for_user,
    get_project_for_user,
    get_recent_projects_for_user,
    mark_project_viewed,
    update_project,
    delete_project,
)
from services.paper_service import get_saved_papers_for_project, count_saved_papers_for_user

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
        project_count = len(get_projects_for_user(db_session, user_id))
        recent_projects = get_recent_projects_for_user(db_session, user_id, limit=3)
        saved_papers_count = count_saved_papers_for_user(db_session, user_id)
    finally:
        db_session.close()

    stats = [
        ("Research Projects", project_count, "📁", "stat-violet"),
        ("Saved Papers", saved_papers_count, "📄", "stat-amber"),
        ("Papers Analysed", 0, "🧠", "stat-teal"),
        ("Potential Gaps Found", 0, "🧭", "stat-rose"),
    ]
    return render_template("dashboard.html", recent_projects=recent_projects, stats=stats)


@main_bp.route("/projects")
@login_required
def projects_list():
    """The 'My Projects' page - every project this user owns, with create/edit/delete."""
    db_session = get_session()
    try:
        projects = get_projects_for_user(db_session, session["user_id"])
    finally:
        db_session.close()

    return render_template("projects.html", projects=projects)


@main_bp.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    db_session = get_session()
    try:
        project = get_project_for_user(db_session, session["user_id"], project_id)
        if project is None:
            # Either this project doesn't exist, or it belongs to someone else - either
            # way, show a plain "not found" rather than leaking which case it is.
            abort(404)
        mark_project_viewed(db_session, project)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    return render_template("project_detail.html", project=project, papers=papers)


@main_bp.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    db_session = get_session()
    try:
        project = get_project_for_user(db_session, session["user_id"], project_id)
        if project is None:
            abort(404)

        if request.method == "GET":
            return render_template("edit_project.html", project=project, errors={}, form={
                "title": project.title,
                "research_question": project.research_question,
                "research_field": project.research_field,
                "keywords": project.keywords,
            })

        title = request.form.get("title", "").strip()
        research_question = request.form.get("research_question", "").strip()
        research_field = request.form.get("research_field", "").strip()
        keywords = request.form.get("keywords", "").strip()

        errors = {}
        if not title:
            errors["title"] = "Please give your project a title."

        if errors:
            return render_template(
                "edit_project.html",
                project=project,
                errors=errors,
                form={
                    "title": title,
                    "research_question": research_question,
                    "research_field": research_field,
                    "keywords": keywords,
                },
            )

        update_project(
            db_session, project,
            title=title, research_question=research_question,
            research_field=research_field, keywords=keywords,
        )
    finally:
        db_session.close()

    flash("Research project updated.", "success")
    return redirect(url_for("main.projects_list"))


@main_bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project_route(project_id):
    db_session = get_session()
    try:
        project = get_project_for_user(db_session, session["user_id"], project_id)
        if project is None:
            abort(404)
        delete_project(db_session, project)
    finally:
        db_session.close()

    flash("Research project deleted.", "success")
    return redirect(url_for("main.projects_list"))


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
        project = create_project(
            db_session,
            user_id=session["user_id"],
            title=title,
            research_question=research_question,
            research_field=research_field,
            keywords=keywords,
        )
        project_id = project.id
    finally:
        db_session.close()

    flash("Research project created.", "success")
    return redirect(url_for("main.project_detail", project_id=project_id))