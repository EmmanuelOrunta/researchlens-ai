# services/project_service.py
#
# Logic for creating and listing a user's research projects. Will grow in Sprint 2+
# (edit, delete, attach saved papers, etc.) - for now it covers exactly what Sprint 1 needs.

from models.project import ResearchProject


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