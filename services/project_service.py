# services/project_service.py
#
# Logic for creating, listing, editing and deleting a user's research projects, plus
# tracking which ones were opened most recently for the dashboard's "Recently viewed"
# section.

from datetime import datetime

from models.project import ResearchProject
from models.saved_paper import SavedPaper


def create_project(session, user_id: int, title: str, research_question: str,
                    research_field: str, keywords: str):
    """Create a new research project for the given user and save it to the database."""
    project = ResearchProject(
        user_id=user_id,
        title=(title or "").strip(),
        research_question=(research_question or "").strip(),
        research_field=(research_field or "").strip(),
        keywords=(keywords or "").strip(),
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def get_projects_for_user(session, user_id: int):
    """Return all research projects belonging to a user, newest first."""
    return (
        session.query(ResearchProject)
        .filter(ResearchProject.user_id == user_id)
        .order_by(ResearchProject.created_at.desc())
        .all()
    )


def get_project_for_user(session, user_id: int, project_id: int):
    """
    Return a single project, but ONLY if it belongs to the given user.
    This is what stops one user from viewing someone else's project just by guessing
    a different id in the URL (e.g. /projects/7) - if the project exists but belongs
    to somebody else, this returns None, same as if it didn't exist at all.
    """
    return (
        session.query(ResearchProject)
        .filter(ResearchProject.id == project_id, ResearchProject.user_id == user_id)
        .first()
    )


def get_recent_projects_for_user(session, user_id: int, limit: int = 3):
    """
    The most recently *viewed* projects, for the dashboard's "Recently viewed" card -
    not the same ordering as get_projects_for_user(), which is newest-created-first.

    A project that's never been opened (last_viewed_at is still NULL) sorts after
    everything that has been, but is not excluded - freshly created projects should
    still show up somewhere. SQLite puts NULLs first in a DESC sort by default, so we
    order by "has it been viewed at all" before last_viewed_at itself to push those
    unopened projects to the back instead.
    """
    return (
        session.query(ResearchProject)
        .filter(ResearchProject.user_id == user_id)
        .order_by(
            ResearchProject.last_viewed_at.isnot(None).desc(),
            ResearchProject.last_viewed_at.desc(),
            ResearchProject.created_at.desc(),
        )
        .limit(limit)
        .all()
    )


def mark_project_viewed(session, project: ResearchProject):
    """
    Stamp a project as just-opened. Called every time its detail page loads.

    session.commit() marks every loaded attribute on `project` as expired, so the next
    time anything touches project.title (etc.) SQLAlchemy tries to re-fetch it from the
    database to get the current value - but by then the route has already closed this
    session, so that re-fetch fails with DetachedInstanceError instead. refresh() here
    reloads those attributes immediately, while the session is still open, so the
    object is safe to hand to render_template() after the session closes.
    """
    project.last_viewed_at = datetime.utcnow()
    session.commit()
    session.refresh(project)


def update_project(session, project: ResearchProject, title: str, research_question: str,
                    research_field: str, keywords: str):
    """Overwrite an existing project's editable fields in place."""
    project.title = (title or "").strip()
    project.research_question = (research_question or "").strip()
    project.research_field = (research_field or "").strip()
    project.keywords = (keywords or "").strip()
    session.commit()
    session.refresh(project)
    return project


def delete_project(session, project: ResearchProject):
    """
    Delete a project. This also removes its SavedPaper links (which papers are in its
    library) first, the same way remove_paper_from_project() does for a single paper -
    otherwise those rows would point at a project_id that no longer exists. The Paper
    rows themselves are left alone, since the same paper might also be saved to a
    different project.
    """
    session.query(SavedPaper).filter(SavedPaper.project_id == project.id).delete()
    session.delete(project)
    session.commit()


def delete_all_projects_for_user(session, user_id: int):
    """
    Wipe every research project this user owns, and the SavedPaper links that point at
    them - the cascade a full account deletion needs (see auth_service.delete_user(),
    called right after this by routes/settings_routes.py). Same idea as delete_project()
    above, just as one bulk delete for every project at once instead of looping
    delete_project() a row at a time.

    As with delete_project(), the Paper rows themselves are left alone - they're not
    owned by any one user, and might still be saved to someone else's project.
    """
    project_ids = [
        row[0] for row in
        session.query(ResearchProject.id).filter(ResearchProject.user_id == user_id).all()
    ]
    if not project_ids:
        return
    session.query(SavedPaper).filter(SavedPaper.project_id.in_(project_ids)).delete(synchronize_session=False)
    session.query(ResearchProject).filter(ResearchProject.id.in_(project_ids)).delete(synchronize_session=False)
    session.commit()