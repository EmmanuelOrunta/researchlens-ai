# routes/papers_routes.py
#
# Everything to do with building up a project's paper library: searching Semantic
# Scholar, saving a result to the project, uploading a PDF directly from your
# computer, and removing a saved paper.
#
# Every route here is scoped to one specific project (the <int:project_id> in the
# URL), and _get_owned_project_or_404 makes sure that project actually belongs to
# whoever is logged in before doing anything else - the same ownership check used on
# the project detail page in main_routes.py.

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort

from services.database_service import get_session
from services.project_service import get_project_for_user
from services.semantic_scholar_service import search_papers
from services.paper_service import (
    get_paper_by_external_id,
    create_paper_from_search_result,
    create_uploaded_paper,
    save_paper_to_project,
    remove_paper_from_project,
)
from services.pdf_service import is_allowed_pdf, save_uploaded_pdf, extract_text_from_pdf

papers_bp = Blueprint("papers", __name__)

# uploads/ lives at the project root, one level up from routes/
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")


def _get_owned_project_or_404(db_session, project_id):
    project = get_project_for_user(db_session, session["user_id"], project_id)
    if project is None:
        abort(404)
    return project


@papers_bp.route("/projects/<int:project_id>/search", methods=["GET"])
def search(project_id):
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
    finally:
        db_session.close()

    query = request.args.get("query", "").strip()
    results = None
    search_error = None

    if query:
        results = search_papers(query)
        if results is None:
            search_error = "Couldn't reach Semantic Scholar right now. Check your internet connection and try again."

    return render_template(
        "paper_search.html",
        project=project,
        query=query,
        results=results,
        search_error=search_error,
    )


@papers_bp.route("/projects/<int:project_id>/papers/save", methods=["POST"])
def save_from_search(project_id):
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

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
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

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
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        remove_paper_from_project(db_session, project_id, paper_id)
    finally:
        db_session.close()

    flash("Paper removed from this project.", "success")
    return redirect(url_for("main.project_detail", project_id=project_id))