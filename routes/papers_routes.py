# routes/papers_routes.py
#
# Everything to do with finding papers, saving them to a project, uploading PDFs
# directly, previewing a saved paper, and browsing papers across all your projects.
#
# Search is always scoped to one project in the URL (/projects/<id>/search) - that's
# where a saved paper ends up. The sidebar's global "Search Papers" link goes through
# choose_project_for_search() first, which works out which project that should be.

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, send_file

from services.database_service import get_session
from services.project_service import get_project_for_user, get_projects_for_user
from services.semantic_scholar_service import search_papers as search_semantic_scholar
from services.openalex_service import search_papers as search_openalex
from services.paper_service import (
    get_paper_by_external_id,
    create_paper_from_search_result,
    create_uploaded_paper,
    save_paper_to_project,
    remove_paper_from_project,
    get_saved_papers_for_project,
    get_all_papers_for_user,
    get_projects_for_paper,
    user_can_access_paper,
)
from services.pdf_service import is_allowed_pdf, save_uploaded_pdf, extract_text_from_pdf
from models.paper import Paper

papers_bp = Blueprint("papers", __name__)

# uploads/ lives at the project root, one level up from routes/
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")


def _require_login():
    """Every route below needs a logged-in user; call this first and return early if it redirects."""
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    return None


def _get_owned_project_or_404(db_session, project_id):
    project = get_project_for_user(db_session, session["user_id"], project_id)
    if project is None:
        abort(404)
    return project


def _search_academic_sources(query, limit=10):
    """
    Try Semantic Scholar first; if it fails outright (no internet, rate-limited, the
    service is down), automatically fall back to OpenAlex instead of just giving up.
    Returns (results, source_label, error_message).
    """
    results = search_semantic_scholar(query, limit=limit)
    if results is not None:
        return results, "Semantic Scholar", None

    results = search_openalex(query, limit=limit)
    if results is not None:
        return results, "OpenAlex", None

    return None, None, (
        "Couldn't reach Semantic Scholar or OpenAlex right now. "
        "Check your internet connection - or the terminal running `python app.py` "
        "usually shows the real error - and try again."
    )


@papers_bp.route("/projects/<int:project_id>/search", methods=["GET"])
def search(project_id):
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
    finally:
        db_session.close()

    query = request.args.get("query", "").strip()
    results = None
    source_used = None
    search_error = None

    if query:
        results, source_used, search_error = _search_academic_sources(query)

    return render_template(
        "paper_search.html",
        project=project,
        query=query,
        results=results,
        source_used=source_used,
        search_error=search_error,
    )


@papers_bp.route("/papers/search")
def choose_project_for_search():
    """
    Entry point for the sidebar's global "Search Papers" link. Since every saved paper
    has to belong to a project, this figures out which one: skips straight to it if
    you only have one project, otherwise asks you to pick.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        projects = get_projects_for_user(db_session, session["user_id"])
    finally:
        db_session.close()

    if not projects:
        flash("Create a research project first, then you can search for papers to add to it.", "error")
        return redirect(url_for("main.new_project"))

    if len(projects) == 1:
        return redirect(url_for("papers.search", project_id=projects[0].id))

    return render_template("choose_project.html", projects=projects)


@papers_bp.route("/papers")
def my_papers():
    """The global 'My Papers' page - every paper saved anywhere, across all your projects."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        entries = get_all_papers_for_user(db_session, session["user_id"])
    finally:
        db_session.close()

    return render_template("my_papers.html", entries=entries)


@papers_bp.route("/papers/<int:paper_id>")
def paper_detail(paper_id):
    """A single paper's preview: full abstract (or extracted PDF text), source link, and which project(s) it's saved to."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        if not user_can_access_paper(db_session, session["user_id"], paper_id):
            abort(404)
        paper = db_session.query(Paper).get(paper_id)
        projects = get_projects_for_paper(db_session, session["user_id"], paper_id)
    finally:
        db_session.close()

    if paper is None:
        abort(404)

    return render_template("paper_detail.html", paper=paper, projects=projects)


@papers_bp.route("/papers/<int:paper_id>/file")
def paper_file(paper_id):
    """Serves an uploaded PDF's actual file - gated by user_can_access_paper so you can't guess another user's paper id."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        if not user_can_access_paper(db_session, session["user_id"], paper_id):
            abort(404)
        paper = db_session.query(Paper).get(paper_id)
    finally:
        db_session.close()

    if paper is None or not paper.file_path or not os.path.exists(paper.file_path):
        abort(404)

    return send_file(paper.file_path, mimetype="application/pdf")


@papers_bp.route("/projects/<int:project_id>/papers", methods=["GET"])
def project_papers(project_id):
    """The full-page view of one project's saved papers (linked from the 'Open' button on the project page)."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    return render_template("project_papers.html", project=project, papers=papers)


@papers_bp.route("/projects/<int:project_id>/papers/save", methods=["POST"])
def save_from_search(project_id):
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)

        external_id = request.form.get("external_id") or None
        existing = get_paper_by_external_id(db_session, external_id)

        if existing:
            paper = existing
        else:
            year_raw = request.form.get("year", "").strip()
            paper = create_paper_from_search_result(db_session, {
                "external_id": external_id,
                "title": request.form.get("title", "Untitled"),
                "authors": request.form.get("authors"),
                "year": int(year_raw) if year_raw.isdigit() else None,
                "abstract": request.form.get("abstract"),
                "doi": request.form.get("doi") or None,
                "url": request.form.get("url") or None,
            })

        save_paper_to_project(db_session, project.id, paper.id)
    finally:
        db_session.close()

    flash("Paper saved to your project.", "success")
    return redirect(url_for("papers.search", project_id=project_id, query=request.form.get("query", "")))


@papers_bp.route("/projects/<int:project_id>/papers/upload", methods=["POST"])
def upload(project_id):
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)

        uploaded_file = request.files.get("pdf_file")
        title = request.form.get("title", "").strip()

        if not uploaded_file or uploaded_file.filename == "":
            flash("Please choose a PDF file to upload.", "error")
            return redirect(url_for("papers.search", project_id=project_id))

        if not is_allowed_pdf(uploaded_file.filename):
            flash("Only PDF files are supported right now.", "error")
            return redirect(url_for("papers.search", project_id=project_id))

        if not title:
            title = os.path.splitext(uploaded_file.filename)[0]

        file_path = save_uploaded_pdf(uploaded_file, UPLOAD_DIR)
        extracted_text = extract_text_from_pdf(file_path)

        paper = create_uploaded_paper(db_session, title=title, file_path=file_path, extracted_text=extracted_text)
        save_paper_to_project(db_session, project.id, paper.id)
    finally:
        db_session.close()

    flash("PDF uploaded and added to your project.", "success")
    return redirect(url_for("main.project_detail", project_id=project_id))


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/remove", methods=["POST"])
def remove(project_id, paper_id):
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        remove_paper_from_project(db_session, project_id, paper_id)
    finally:
        db_session.close()

    flash("Paper removed from this project.", "success")
    return redirect(url_for("main.project_detail", project_id=project_id))