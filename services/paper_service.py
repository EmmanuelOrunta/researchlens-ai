# services/paper_service.py
#
# Logic for turning search results / uploaded PDFs into Paper rows, and for managing
# which papers are saved to which research project (the "research library" from the
# project plan).

from models.paper import Paper
from models.saved_paper import SavedPaper
from models.project import ResearchProject


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
    """Insert a Paper row from a Semantic Scholar search result dict."""
    paper = Paper(
        title=data.get("title") or "Untitled",
        authors=data.get("authors"),
        year=data.get("year"),
        abstract=data.get("abstract"),
        doi=data.get("doi"),
        url=data.get("url"),
        source="semantic_scholar",
        external_id=data.get("external_id"),
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