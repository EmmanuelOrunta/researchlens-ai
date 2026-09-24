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
from services.project_service import get_project_for_user, get_projects_for_user, set_project_synthesis
from services.semantic_scholar_service import search_papers as search_semantic_scholar
from services.openalex_service import search_papers as search_openalex
from services.paper_service import (
    get_paper_by_external_id,
    create_paper_from_search_result,
    create_uploaded_paper,
    save_paper_to_project,
    remove_paper_from_project,
    get_saved_papers_for_project,
    get_relevance_rating,
    get_saved_paper_entries_for_project,
    get_saved_paper,
    get_all_papers_for_user,
    get_ai_analysis_overview_for_user,
    get_projects_for_paper,
    user_can_access_paper,
    set_paper_summary,
    set_saved_paper_relevance,
    set_paper_matrix_fields,
    get_or_fetch_source_text,
    get_note_counts_for_saved_paper_ids,
    get_note,
    create_note,
    update_note,
    delete_note,
    ensure_legacy_notes_migrated,
    build_synthesis_capsule,
)
from services.pdf_service import is_allowed_pdf, save_uploaded_pdf, extract_text_from_pdf
from services.openai_service import (
    is_configured as openai_is_configured,
    stream_summarize_paper,
    stream_analyze_relevance,
    stream_extract_matrix_fields,
    stream_synthesize_papers,
)
from services.export_service import build_matrix_excel, build_matrix_pdf, build_matrix_docx, export_filename
from models.paper import Paper
from models.project import ResearchProject

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


@papers_bp.route("/matrix")
def choose_project_for_matrix():
    """
    Entry point for the sidebar's global "Literature Matrix" link. A matrix only makes
    sense within one project's literature (comparing papers against one project's own
    research question), so - exactly like choose_project_for_search() above - this
    skips straight to a lone project's matrix, or asks which project otherwise.
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
        flash("Create a research project and save some papers to it first, then you can build its literature matrix.", "error")
        return redirect(url_for("main.new_project"))

    if len(projects) == 1:
        return redirect(url_for("papers.literature_matrix", project_id=projects[0].id))

    return render_template(
        "choose_project.html", projects=projects,
        next_endpoint="papers.literature_matrix",
        heading="Which project's literature matrix?",
        subtitle="The comparison table is built from one project's saved papers at a time.",
    )


@papers_bp.route("/projects/<int:project_id>/matrix", methods=["GET"])
def literature_matrix(project_id):
    """
    The Literature Matrix (Sprint 4, started early): a comparison table across every
    paper saved to this project, with AI-extracted (and directly user-editable)
    Methodology / Sample / Findings / Limitations fields for each - see
    templates/literature_matrix.html. The four fields live on Paper (see
    models/paper.py), same as the AI Summary, so they're shared if the same paper is
    also saved to another project - only which papers show up here is project-scoped.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    return render_template(
        "literature_matrix.html", project=project, papers=papers,
        openai_configured=openai_is_configured(),
    )


@papers_bp.route("/projects/<int:project_id>/matrix/export.xlsx", methods=["GET"])
def export_matrix_excel(project_id):
    """Download the Literature Matrix as an Excel workbook - see services/export_service.py."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    buffer = build_matrix_excel(project, papers)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=export_filename(project, "xlsx"),
    )


@papers_bp.route("/projects/<int:project_id>/matrix/export.docx", methods=["GET"])
def export_matrix_docx(project_id):
    """Download the Literature Matrix as a Word document - see services/export_service.py."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    buffer = build_matrix_docx(project, papers)
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=export_filename(project, "docx"),
    )


@papers_bp.route("/projects/<int:project_id>/matrix/export.pdf", methods=["GET"])
def export_matrix_pdf(project_id):
    """Download the Literature Matrix as a PDF - see services/export_service.py."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)
    finally:
        db_session.close()

    buffer = build_matrix_pdf(project, papers)
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=export_filename(project, "pdf"),
    )


@papers_bp.route("/synthesis")
def choose_project_for_synthesis():
    """
    Entry point for the sidebar's "Paper Synthesis" link - exactly like
    choose_project_for_matrix() above, a synthesis only makes sense within one
    project's saved papers, so this skips straight to a lone project's synthesis page,
    or asks which project otherwise.
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
        flash("Create a research project and save some papers to it first, then you can build a synthesis.", "error")
        return redirect(url_for("main.new_project"))

    if len(projects) == 1:
        return redirect(url_for("papers.paper_synthesis", project_id=projects[0].id))

    return render_template(
        "choose_project.html", projects=projects,
        next_endpoint="papers.paper_synthesis",
        heading="Which project's papers do you want to synthesize?",
        subtitle="The synthesis draws on whichever papers you select from one project's saved library.",
    )


@papers_bp.route("/projects/<int:project_id>/synthesis", methods=["GET"])
def paper_synthesis(project_id):
    """
    Paper Synthesis (Sprint 4): a single flowing, multi-paragraph AI narrative across
    whichever of this project's saved papers the user selects - summarizing,
    synthesizing, comparing, and critiquing them together, the way a literature
    review's own "Synthesis Review" section would (as opposed to the Literature
    Matrix's row-by-row structured comparison). See templates/paper_synthesis.html and
    services/openai_service.py's stream_synthesize_papers().

    selected_ids pre-checks whichever papers the CURRENT synthesis_text (if any) was
    generated from, and synthesis_papers resolves those same ids to full Paper objects
    (for the "Based on: ..." line) - both computed here rather than in the template,
    since project.synthesis_paper_ids is just a raw comma-separated string on the model.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        papers = get_saved_papers_for_project(db_session, project_id)

        selected_ids = set()
        synthesis_papers = []
        if project.synthesis_paper_ids:
            ids = [int(pid) for pid in project.synthesis_paper_ids.split(",") if pid.strip().isdigit()]
            papers_by_id = {paper.id: paper for paper in papers}
            selected_ids = {pid for pid in ids if pid in papers_by_id}
            synthesis_papers = [papers_by_id[pid] for pid in ids if pid in papers_by_id]
    finally:
        db_session.close()

    return render_template(
        "paper_synthesis.html", project=project, papers=papers,
        selected_ids=selected_ids, synthesis_papers=synthesis_papers,
        openai_configured=openai_is_configured(),
    )


@papers_bp.route("/projects/<int:project_id>/synthesis/stream", methods=["POST"])
def synthesis_stream(project_id):
    """
    Streams the Paper Synthesis live, one chunk of text at a time - see
    summarize_stream() below for the NDJSON event shapes and the two-phase session
    lifecycle this follows. Unlike every other AI stream route in this file, the set of
    papers to use isn't fixed by the URL - it comes from the request body (repeated
    paper_ids=<id> fields, one per checked box - see templates/paper_synthesis.html and
    static/js/app.js's [data-stream-url] handler's data-paper-checkbox-name support),
    since which papers to synthesize is a per-generation choice the user makes each
    time, not something tied to a single paper or a fixed project setting.

    Submitted ids are re-validated against this project's OWN saved papers server-side
    (never trusting the client's list outright) and de-duplicated while preserving
    submission order, the same defense-in-depth every other route here applies to
    user-supplied ids.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    requested_ids = [int(pid) for pid in request.form.getlist("paper_ids") if pid.strip().isdigit()]

    db_session = get_session()
    try:
        project = _get_owned_project_or_404(db_session, project_id)
        project_papers = get_saved_papers_for_project(db_session, project_id)
        papers_by_id = {paper.id: paper for paper in project_papers}

        seen = set()
        ordered_ids = []
        for pid in requested_ids:
            if pid in papers_by_id and pid not in seen:
                seen.add(pid)
                ordered_ids.append(pid)

        project_title = project.title
        research_question = project.research_question
        capsules = [
            {
                "title": papers_by_id[pid].title,
                "authors": papers_by_id[pid].authors,
                "year": papers_by_id[pid].year,
                "capsule": build_synthesis_capsule(papers_by_id[pid]),
            }
            for pid in ordered_ids
        ]
    finally:
        db_session.close()

    def generate():
        if len(ordered_ids) < 2:
            yield json.dumps({"error": "Select at least 2 papers to synthesize."}) + "\n"
            return
        for event in stream_synthesize_papers(project_title, research_question, capsules):
            if event.get("done"):
                write_session = get_session()
                try:
                    fresh_project = write_session.query(ResearchProject).get(project_id)
                    if fresh_project is not None:
                        set_project_synthesis(write_session, fresh_project, event["text"], ordered_ids)
                finally:
                    write_session.close()
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/matrix/edit", methods=["POST"])
def edit_matrix_fields(project_id, paper_id):
    """
    Manually edit (or hand-correct an AI extraction of) this paper's four Literature
    Matrix fields - the matrix is AI-extracted but directly user-editable, unlike the
    AI Summary. Scoped under a project in the URL only so the redirect lands back on
    that project's matrix page; the fields themselves are saved on the Paper (shared
    across every project it's saved to), via set_paper_matrix_fields().
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        paper = db_session.query(Paper).get(paper_id)
        if paper is None or not user_can_access_paper(db_session, session["user_id"], paper_id):
            abort(404)
        set_paper_matrix_fields(
            db_session, paper,
            methodology=request.form.get("methodology", ""),
            sample=request.form.get("sample", ""),
            findings=request.form.get("findings", ""),
            limitations=request.form.get("limitations", ""),
        )
    finally:
        db_session.close()

    flash("Literature matrix row updated.", "success")
    return redirect(url_for("papers.literature_matrix", project_id=project_id))


@papers_bp.route("/papers/<int:paper_id>/matrix/stream", methods=["POST"])
def matrix_extract_stream(paper_id):
    """
    Streams this paper's four Literature Matrix fields live, one chunk of text at a
    time, exactly like summarize_stream() below - see that function's docstring for the
    NDJSON event shapes and the two-phase session lifecycle this follows. Not scoped to
    a project for the same reason summarize_stream() isn't: the extracted fields live
    on Paper and are shared across every project the paper is saved to.

    On {"done": true}, the full text is split back into its four blank-line-separated
    paragraphs (see stream_extract_matrix_fields()'s system prompt) and stored via
    set_paper_matrix_fields() - static/js/app.js's [data-stream-url] handler does the
    same split independently, purely for rendering, into this row's four table cells
    (via data-targets) as the text streams in.
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
        authors = paper.authors
        year = paper.year
        source_text, text_error = get_or_fetch_source_text(db_session, paper)
    finally:
        db_session.close()

    def generate():
        if text_error:
            yield json.dumps({"error": text_error}) + "\n"
            return
        for event in stream_extract_matrix_fields(title, authors, year, source_text):
            if event.get("done"):
                fields = [p.strip() for p in event["text"].split("\n\n") if p.strip()]
                fields += [""] * (4 - len(fields))  # pad, in case the model returns fewer than four
                write_session = get_session()
                try:
                    fresh_paper = write_session.query(Paper).get(paper_id)
                    if fresh_paper is not None:
                        set_paper_matrix_fields(
                            write_session, fresh_paper,
                            methodology=fields[0], sample=fields[1],
                            findings=fields[2], limitations=fields[3],
                        )
                finally:
                    write_session.close()
            yield json.dumps(event) + "\n"

    return Response(generate(), mimetype="application/x-ndjson")


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


@papers_bp.route("/analysis")
def ai_analysis():
    """
    The "AI Paper Analysis" hub (Sprint 3): every paper saved anywhere across your
    projects, with its AI Summary status and how many of its project(s) have a
    relevance analysis - so you can see at a glance what still needs attention rather
    than checking each project separately. Linked from the sidebar's "AI Paper
    Analysis" item, distinct from "My Papers" (which is about browsing paper details,
    not analysis status).
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        overview = get_ai_analysis_overview_for_user(db_session, session["user_id"])
    finally:
        db_session.close()

    return render_template(
        "ai_analysis.html", overview=overview, openai_configured=openai_is_configured(),
    )


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
        pairs = get_saved_paper_entries_for_project(db_session, project_id)
        note_counts = get_note_counts_for_saved_paper_ids(db_session, [sp.id for _, sp in pairs])
        entries = [
            {
                "paper": paper, "saved_paper": saved_paper,
                "note_count": note_counts.get(saved_paper.id, 0),
                "relevance_rating": get_relevance_rating(saved_paper.relevance_analysis),
            }
            for paper, saved_paper in pairs
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
        notes = ensure_legacy_notes_migrated(db_session, saved_paper)
    finally:
        db_session.close()

    return render_template(
        "project_paper_detail.html", project=project, paper=paper, saved_paper=saved_paper,
        notes=notes, openai_configured=openai_is_configured(),
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
        authors = paper.authors
        year = paper.year
        source_text, text_error = get_or_fetch_source_text(db_session, paper)
    finally:
        db_session.close()

    def generate():
        if text_error:
            yield json.dumps({"error": text_error}) + "\n"
            return
        for event in stream_summarize_paper(title, authors, year, source_text):
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


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/notes/add", methods=["POST"])
def add_note(project_id, paper_id):
    """
    Add a new note to this saved paper, within this project - each note is its own
    independent entry (its own optional title and content), like adding a new file
    rather than appending to a shared block of text. See project_paper_detail.html's
    "+ Add Note" panel.
    """
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        content = request.form.get("content", "").strip()
        title = request.form.get("title", "").strip()
        if content:
            create_note(db_session, saved_paper.id, content, title)
            flash("Note added.", "success")
        else:
            flash("Can't add an empty note - write something first.", "error")
    finally:
        db_session.close()

    return redirect(url_for("papers.project_paper_detail", project_id=project_id, paper_id=paper_id))


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/notes/<int:note_id>/edit", methods=["POST"])
def edit_note(project_id, paper_id, note_id):
    """Save edits to one existing note on this saved paper (title and/or content)."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        note = get_note(db_session, saved_paper.id, note_id)
        if note is None:
            abort(404)
        content = request.form.get("content", "").strip()
        title = request.form.get("title", "").strip()
        if content:
            update_note(db_session, note, content, title)
            flash("Note updated.", "success")
        else:
            flash("Can't save an empty note - delete it instead if you don't need it anymore.", "error")
    finally:
        db_session.close()

    return redirect(url_for("papers.project_paper_detail", project_id=project_id, paper_id=paper_id))


@papers_bp.route("/projects/<int:project_id>/papers/<int:paper_id>/notes/<int:note_id>/delete", methods=["POST"])
def delete_note_route(project_id, paper_id, note_id):
    """Delete one note from this saved paper."""
    redirect_response = _require_login()
    if redirect_response:
        return redirect_response

    db_session = get_session()
    try:
        _get_owned_project_or_404(db_session, project_id)
        saved_paper = get_saved_paper(db_session, project_id, paper_id)
        if saved_paper is None:
            abort(404)
        note = get_note(db_session, saved_paper.id, note_id)
        if note is not None:
            delete_note(db_session, note)
            flash("Note deleted.", "success")
    finally:
        db_session.close()

    return redirect(url_for("papers.project_paper_detail", project_id=project_id, paper_id=paper_id))