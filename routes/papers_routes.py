# routes/papers_routes.py
#
# Everything to do with finding papers, saving them to a project, uploading PDFs
# directly, previewing a saved paper, and browsing papers across all your projects.
#
# Search is always scoped to one project in the URL (/projects/<id>/search) - that's
# where a saved paper ends up. The sidebar's global "Search Papers" link goes through
# choose_project_for_search() first, which works out which project that should be.

import os
import re
import math
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, abort, send_file, Response

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
    get_saved_paper_entries_for_project,
    get_saved_paper,
    get_all_papers_for_user,
    get_projects_for_paper,
    user_can_access_paper,
    set_paper_summary,
    update_saved_paper_notes,
    set_saved_paper_relevance,
    get_or_fetch_source_text,
)
from services.pdf_service import is_allowed_pdf, save_uploaded_pdf, extract_text_from_pdf
from services.openai_service import (
    is_configured as openai_is_configured,
    stream_summarize_paper,
    stream_analyze_relevance,
)
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


SEARCH_FETCH_LIMIT_PER_SOURCE = 100  # how many results to pull from EACH API per search
SEARCH_PAGE_SIZE = 10                # how many merged results to show per page

# 100 is Semantic Scholar's own hard ceiling for a single request on the search
# endpoint this app calls (see MAX_LIMIT in semantic_scholar_service.py) - it's the
# most this app can pull from that source per search without adding real upstream
# pagination. OpenAlex allows up to 200 per request, but both are fetched at the same
# number here so the round-robin merge below draws roughly evenly from each rather
# than always running out of one source first.

SOURCE_LABELS = {"semantic_scholar": "Semantic Scholar", "openalex": "OpenAlex"}


def _dedupe_key(paper):
    """
    Semantic Scholar and OpenAlex will often return the very same paper - a DOI is the
    most reliable way to recognise that, since it's a stable identifier assigned once
    to a publication regardless of which index is reporting it. When a paper has no
    DOI (common for preprints, some conference papers, etc.), fall back to a loosely
    normalised title instead - good enough to catch obvious duplicates without being so
    strict that unrelated papers with slightly different titles collide.
    """
    doi = (paper.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9]+", " ", (paper.get("title") or "").lower()).strip()
    return f"title:{title}"


def _search_academic_sources(query, limit_per_source=SEARCH_FETCH_LIMIT_PER_SOURCE):
    """
    Query Semantic Scholar AND OpenAlex (rather than only falling back to the second
    one if the first fails), tag every result with which of the two it came from, and
    merge them round-robin (one from Semantic Scholar, one from OpenAlex, repeat) so
    the combined list roughly reflects both engines' own relevance ranking instead of
    dumping all of one source before any of the other. Duplicates (the same paper
    showing up in both) are dropped, keeping whichever copy was seen first.

    Returns (merged_results, sources_used, error_message). sources_used lists which
    API(s) actually responded, even if one of them found zero results - it's only
    excluded if the request failed outright. error_message is only set if BOTH
    sources failed.
    """
    ss_results = search_semantic_scholar(query, limit=limit_per_source)
    oa_results = search_openalex(query, limit=limit_per_source)

    if ss_results is not None:
        for paper in ss_results:
            paper["source"] = "semantic_scholar"
    if oa_results is not None:
        for paper in oa_results:
            paper["source"] = "openalex"

    if ss_results is None and oa_results is None:
        return [], [], (
            "Couldn't reach Semantic Scholar or OpenAlex right now. "
            "Check your internet connection - or the terminal running `python app.py` "
            "usually shows the real error - and try again."
        )

    # One source failing outright (rather than both) isn't a hard error - there are
    # still results to show - but it's exactly why a search can look OpenAlex-heavy: if
    # Semantic Scholar's shared, unauthenticated rate limit rejected this request, every
    # result below is quietly coming from OpenAlex alone. Surface that instead of
    # letting it look like Semantic Scholar simply had nothing relevant to say.
    partial_warning = None
    if ss_results is None:
        partial_warning = (
            "Semantic Scholar didn't respond to this search (likely rate-limited - its "
            "free tier is shared across everyone using it without a personal API key), "
            "so these results are from OpenAlex only. Add a free SEMANTIC_SCHOLAR_API_KEY "
            "in .env for more reliable results - see .env.example."
        )
    elif oa_results is None:
        partial_warning = "OpenAlex didn't respond to this search, so these results are from Semantic Scholar only."

    lists = [results for results in (ss_results, oa_results) if results is not None]
    sources_used = [SOURCE_LABELS[results[0]["source"]] for results in lists if results]
    # A source can respond successfully with zero hits - still worth showing it was
    # consulted, so fall back to labelling it from whichever list is empty-but-present.
    if len(sources_used) < len(lists):
        sources_used = [
            SOURCE_LABELS["semantic_scholar"] if results is ss_results else SOURCE_LABELS["openalex"]
            for results in lists
        ]

    merged = []
    seen_keys = set()
    max_len = max((len(results) for results in lists), default=0)
    for i in range(max_len):
        for results in lists:
            if i >= len(results):
                continue
            key = _dedupe_key(results[i])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged.append(results[i])

    return merged, sources_used, partial_warning


def _filter_by_year(results, year_from, year_to):
    """Drop anything outside [year_from, year_to]. A paper with no known year is
    excluded whenever a year filter is active, since we can't confirm it belongs."""
    if year_from is None and year_to is None:
        return results

    def in_range(paper):
        year = paper.get("year")
        if year is None:
            return False
        if year_from is not None and year < year_from:
            return False
        if year_to is not None and year > year_to:
            return False
        return True

    return [paper for paper in results if in_range(paper)]


def _sort_results(results, sort):
    if sort == "newest":
        return sorted(results, key=lambda p: p.get("year") if p.get("year") is not None else -9999, reverse=True)
    if sort == "oldest":
        return sorted(results, key=lambda p: p.get("year") if p.get("year") is not None else 9999)
    return results  # "relevance" (default) - keep the merged order as-is


def _parse_year_arg(raw_value):
    raw_value = (raw_value or "").strip()
    if not raw_value.isdigit():
        return None
    return int(raw_value)


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
    year_from_raw = request.args.get("year_from", "").strip()
    year_to_raw = request.args.get("year_to", "").strip()
    sort = request.args.get("sort", "relevance")
    if sort not in ("relevance", "newest", "oldest"):
        sort = "relevance"

    year_from = _parse_year_arg(year_from_raw)
    year_to = _parse_year_arg(year_to_raw)

    results = None
    sources_used = []
    search_error = None
    total_count = 0
    total_pages = 1
    page = request.args.get("page", 1, type=int) or 1

    if query:
        all_results, sources_used, search_error = _search_academic_sources(query)
        all_results = _filter_by_year(all_results, year_from, year_to)
        all_results = _sort_results(all_results, sort)

        total_count = len(all_results)
        total_pages = max(1, math.ceil(total_count / SEARCH_PAGE_SIZE))
        page = max(1, min(page, total_pages))
        start = (page - 1) * SEARCH_PAGE_SIZE
        results = all_results[start:start + SEARCH_PAGE_SIZE]

    return render_template(
        "paper_search.html",
        project=project,
        query=query,
        results=results,
        sources_used=sources_used,
        search_error=search_error,
        year_from=year_from_raw,
        year_to=year_to_raw,
        sort=sort,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
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

    return render_template(
        "paper_detail.html", paper=paper, projects=projects,
        openai_configured=openai_is_configured(),
    )


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
        entries = [
            {"paper": paper, "saved_paper": saved_paper}
            for paper, saved_paper in get_saved_paper_entries_for_project(db_session, project_id)
        ]
    finally:
        db_session.close()

    return render_template(
        "project_papers.html", project=project, entries=entries,
        openai_configured=openai_is_configured(),
    )


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>", methods=["GET"])
def project_paper_detail(project_id, paper_id):
    """
    A single saved paper's own page within this project - its AI summary, this
    project's relevance analysis, and this project's notes, all together, without
    scrolling past every other saved paper first. This is the destination
    project_papers.html's compact list links to (Sprint 3, Feature 1).
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        paper = db_session.query(Paper).get(paper_id)
        if paper is None:
            abort(404)
    finally:
        db_session.close()

    return render_template(
        "project_paper_detail.html", project=project, paper=paper, saved_paper=saved_paper,
        openai_configured=openai_is_configured(),
    )


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
                "source": request.form.get("source") or "semantic_scholar",
                "open_access_pdf_url": request.form.get("open_access_pdf_url") or None,
            })

        save_paper_to_project(db_session, project.id, paper.id)
    finally:
        db_session.close()

    flash("Paper saved to your project.", "success")
    return redirect(url_for(
        "papers.search", project_id=project_id,
        query=request.form.get("query", ""),
        year_from=request.form.get("year_from", ""),
        year_to=request.form.get("year_to", ""),
        sort=request.form.get("sort", "relevance"),
        page=request.form.get("page", 1),
    ))


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


# --- Sprint 3: AI summaries, per-project relevance analysis, and per-project notes ---


@papers_bp.route("/papers/<int:paper_id>/summarize/stream", methods=["POST"])
def summarize_stream(paper_id):
    """
    Streams a paper's AI summary live, one chunk of text at a time, so the page can
    show it "typing" in the way ChatGPT does instead of appearing all at once. Not
    scoped to a project - a paper's summary is the same no matter which project you're
    viewing it from.

    Ships the response as NDJSON (newline-delimited JSON: one JSON object per line) -
    see static/js/app.js's [data-stream-url] handler for how the page reads this
    incrementally. Each line is one of:
      {"delta": "..."}            - append this chunk of text
      {"error": "..."}            - show this message instead; nothing was saved
      {"done": true, "text": "…"} - generation finished; this is the full text

    Uses a two-phase session lifecycle because Flask only starts iterating a streamed
    Response's generator AFTER this view function has already returned - by which
    point any session opened here would already be closed. Phase one (below,
    synchronous, before the Response is built) does the access check and resolves the
    source text using a short-lived session. Phase two (inside generate(), lazily run
    once this function returns) opens its OWN fresh session only at the moment it
    needs to persist the finished summary, re-querying the paper by id rather than
    reusing phase one's already-closed object.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        if not user_can_access_paper(db_session, session["user_id"], paper_id):
            abort(404)
        paper = db_session.query(Paper).get(paper_id)
        if paper is None:
            abort(404)
        title = paper.title
        source_text, text_error = get_or_fetch_source_text(db_session, paper)
    finally:
        db_session.close()

    def generate():
        if text_error:
            yield json.dumps({"error": text_error}) + "\n"
            return
        for event in stream_summarize_paper(title, source_text):
            if event.get("done"):
                write_session = get_session()
                try:
                    fresh_paper = write_session.query(Paper).get(paper_id)
                    if fresh_paper is not None:
                        set_paper_summary(write_session, fresh_paper, event["text"])
                finally:
                    write_session.close()
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/relevance/stream", methods=["POST"])
def generate_relevance_stream(project_id, paper_id):
    """
    Streams how relevant this paper is to THIS project specifically, live, one chunk
    at a time - judged against the project's own research question/field/keywords,
    which is why (unlike summarize_stream() above) this route is scoped to one
    project. See summarize_stream() above for the NDJSON event shapes and the
    two-phase session lifecycle this follows.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        paper = db_session.query(Paper).get(paper_id)
        if paper is None:
            abort(404)
        paper_title = paper.title
        research_question = project.research_question
        research_field = project.research_field
        keywords = project.keywords
        source_text, text_error = get_or_fetch_source_text(db_session, paper)
    finally:
        db_session.close()

    def generate():
        if text_error:
            yield json.dumps({"error": text_error}) + "\n"
            return
        for event in stream_analyze_relevance(
            paper_title, source_text, research_question, research_field, keywords,
        ):
            if event.get("done"):
                write_session = get_session()
                try:
                    fresh_saved_paper = get_saved_paper(write_session, project_id, paper_id)
                    if fresh_saved_paper is not None:
                        set_saved_paper_relevance(write_session, fresh_saved_paper, event["text"])
                finally:
                    write_session.close()
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/notes", methods=["POST"])
def save_notes(project_id, paper_id):
    """Save this paper's free-form notes within this one project."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        update_saved_paper_notes(db_session, saved_paper, request.form.get("notes", "").strip())
    finally:
        db_session.close()

    flash("Notes saved.", "success")
    return redirect(url_for("papers.project_paper_detail", project_id=project_id, paper_id=paper_id))