# services/paper_service.py
#
# Logic for turning search results / uploaded PDFs into Paper rows, and for managing
# which papers are saved to which research project (the "research library" from the
# project plan).

from datetime import datetime

from models.paper import Paper
from models.saved_paper import SavedPaper
from models.project import ResearchProject
from services.pdf_service import fetch_and_extract_text_from_url


def get_paper_by_external_id(session, external_id: str):
    """
    Look up a paper we've already saved before, by Semantic Scholar's paperId.
    Used to avoid storing the same paper twice if two different projects (or two
    searches) both save it.
    """
    if not external_id:
        return None
    return session.query(Paper).filter(Paper.external_id == external_id).first()


def create_paper_from_search_result(session, data: dict) -> Paper:
    """
    Insert a Paper row from a search result dict - either Semantic Scholar's or
    OpenAlex's shape, both normalised to the same keys by their respective services.
    `data["source"]` records which one it actually came from ("semantic_scholar" or
    "openalex"), defaulting to "semantic_scholar" only for backward compatibility with
    any old bookmarked save requests that predate the OpenAlex integration.
    """
    paper = Paper(
        title=data.get("title") or "Untitled",
        authors=data.get("authors"),
        year=data.get("year"),
        abstract=data.get("abstract"),
        doi=data.get("doi"),
        url=data.get("url"),
        source=data.get("source") or "semantic_scholar",
        external_id=data.get("external_id"),
        open_access_pdf_url=data.get("open_access_pdf_url"),
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)
    return paper


def create_uploaded_paper(session, title: str, file_path: str, extracted_text: str) -> Paper:
    """Insert a Paper row for a PDF the user uploaded directly."""
    paper = Paper(
        title=title or "Untitled",
        source="upload",
        file_path=file_path,
        extracted_text=extracted_text,
    )
    session.add(paper)
    session.commit()
    session.refresh(paper)
    return paper


def is_paper_saved_to_project(session, project_id: int, paper_id: int) -> bool:
    return (
        session.query(SavedPaper)
        .filter(SavedPaper.project_id == project_id, SavedPaper.paper_id == paper_id)
        .first()
        is not None
    )


def save_paper_to_project(session, project_id: int, paper_id: int):
    """Add a paper to a project's library, unless it's already there."""
    if is_paper_saved_to_project(session, project_id, paper_id):
        return
    session.add(SavedPaper(project_id=project_id, paper_id=paper_id))
    session.commit()


def get_saved_papers_for_project(session, project_id: int):
    """Return the Paper rows saved to this project, most recently saved first."""
    return (
        session.query(Paper)
        .join(SavedPaper, SavedPaper.paper_id == Paper.id)
        .filter(SavedPaper.project_id == project_id)
        .order_by(SavedPaper.saved_at.desc())
        .all()
    )


def remove_paper_from_project(session, project_id: int, paper_id: int):
    """
    Remove a paper from a project's library. This only deletes the link between the
    project and the paper (the SavedPaper row) - the Paper itself stays in the
    database, in case it's also saved to another project.
    """
    session.query(SavedPaper).filter(
        SavedPaper.project_id == project_id, SavedPaper.paper_id == paper_id
    ).delete()
    session.commit()


def count_saved_papers_for_user(session, user_id: int) -> int:
    """Total papers saved across ALL of a user's projects - used on the dashboard stat card."""
    return (
        session.query(SavedPaper)
        .join(ResearchProject, ResearchProject.id == SavedPaper.project_id)
        .filter(ResearchProject.user_id == user_id)
        .count()
    )


def get_projects_for_paper(session, user_id: int, paper_id: int):
    """
    Which of this user's projects has this paper saved to it? A paper can belong to
    more than one project, which is why this returns a list rather than a single one.
    """
    return (
        session.query(ResearchProject)
        .join(SavedPaper, SavedPaper.project_id == ResearchProject.id)
        .filter(SavedPaper.paper_id == paper_id, ResearchProject.user_id == user_id)
        .all()
    )


def user_can_access_paper(session, user_id: int, paper_id: int) -> bool:
    """
    True if this paper is saved to at least one of the user's projects. Used before
    showing a paper's preview or serving its PDF file, so one user can't view another
    user's uploaded paper just by guessing a paper id in the URL.
    """
    return len(get_projects_for_paper(session, user_id, paper_id)) > 0


def get_all_papers_for_user(session, user_id: int):
    """
    Every paper saved anywhere across this user's projects (the global "My Papers"
    page), paired with the project(s) each one belongs to. Returns a list of
    {"paper": Paper, "projects": [ResearchProject, ...]} dicts.
    """
    papers = (
        session.query(Paper)
        .join(SavedPaper, SavedPaper.paper_id == Paper.id)
        .join(ResearchProject, ResearchProject.id == SavedPaper.project_id)
        .filter(ResearchProject.user_id == user_id)
        .distinct()
        .order_by(Paper.created_at.desc())
        .all()
    )

    return [
        {"paper": paper, "projects": get_projects_for_paper(session, user_id, paper.id)}
        for paper in papers
    ]


# --- Sprint 3: AI summaries, per-project relevance analysis, and per-project notes ---


def set_paper_summary(session, paper: Paper, summary: str) -> Paper:
    """Store an AI-generated summary on a paper (see services/openai_service.py's
    summarize_paper()). Shared across every project the paper is saved to."""
    paper.summary = summary
    paper.summary_generated_at = datetime.utcnow()
    session.commit()
    session.refresh(paper)
    return paper


def get_saved_paper(session, project_id: int, paper_id: int):
    """
    The SavedPaper link row for one paper in one project - this is where per-project
    notes and relevance analysis live (see models/saved_paper.py), so routes fetch
    this row before reading or writing either one.
    """
    return (
        session.query(SavedPaper)
        .filter(SavedPaper.project_id == project_id, SavedPaper.paper_id == paper_id)
        .first()
    )


def get_saved_paper_entries_for_project(session, project_id: int):
    """
    Like get_saved_papers_for_project(), but returns (Paper, SavedPaper) pairs instead
    of bare Paper rows - project_papers.html needs the SavedPaper side too, since
    that's where this project's notes and relevance analysis for each paper live.
    """
    return (
        session.query(Paper, SavedPaper)
        .join(SavedPaper, SavedPaper.paper_id == Paper.id)
        .filter(SavedPaper.project_id == project_id)
        .order_by(SavedPaper.saved_at.desc())
        .all()
    )


def update_saved_paper_notes(session, saved_paper: SavedPaper, notes: str) -> SavedPaper:
    """Overwrite this paper's free-form notes within this one project."""
    saved_paper.notes = notes or None
    session.commit()
    session.refresh(saved_paper)
    return saved_paper


def set_saved_paper_relevance(session, saved_paper: SavedPaper, analysis: str) -> SavedPaper:
    """Store an AI-generated relevance analysis for this paper, within this one
    project (see services/openai_service.py's analyze_relevance())."""
    saved_paper.relevance_analysis = analysis
    saved_paper.relevance_generated_at = datetime.utcnow()
    session.commit()
    session.refresh(saved_paper)
    return saved_paper


def get_or_fetch_source_text(session, paper: Paper):
    """
    Whatever text Sprint 3's AI features (summarize_paper(), analyze_relevance()) can
    actually read for this paper - preferring what's already stored, only reaching out
    to the network as a last resort:

      1. paper.abstract, if the source API provided one
      2. paper.extracted_text, if this was a direct upload (or already fetched below,
         on a previous call - so this only ever downloads a given paper's PDF once)
      3. otherwise, if the source API told us this paper has an open-access copy
         (paper.open_access_pdf_url - see semantic_scholar_service.py and
         openalex_service.py), download and extract it via
         pdf_service.fetch_and_extract_text_from_url()

    Returns (text, error) - exactly one is set. text is never an empty string (that's
    treated as an error case too), so callers can rely on `if text:`.
    """
    if paper.abstract:
        return paper.abstract, None
    if paper.extracted_text:
        return paper.extracted_text, None

    if not paper.open_access_pdf_url:
        return None, (
            "This paper has no abstract, and its source didn't provide an "
            "open-access PDF to read instead."
        )

    text, fetch_error = fetch_and_extract_text_from_url(paper.open_access_pdf_url)
    if fetch_error:
        return None, fetch_error

    paper.extracted_text = text
    session.commit()
    session.refresh(paper)
    return text, None


def count_summarized_papers_for_user(session, user_id: int) -> int:
    """
    How many distinct papers (across all of a user's projects) have an AI summary -
    powers the dashboard's "Papers Analysed" stat card.
    """
    return (
        session.query(Paper.id)
        .join(SavedPaper, SavedPaper.paper_id == Paper.id)
        .join(ResearchProject, ResearchProject.id == SavedPaper.project_id)
        .filter(ResearchProject.user_id == user_id, Paper.summary.isnot(None))
        .distinct()
        .count()
    )