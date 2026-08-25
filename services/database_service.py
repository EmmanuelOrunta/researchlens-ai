# services/database_service.py
#
# This file sets up the connection to our SQLite database.
# SQLite stores the entire database as a single file on disk (database/researchlens.db) -
# there's no separate database server to install or run, which is why the project plan
# chose it for a local prototype.
#
# This file is framework-agnostic (no Flask/Streamlit-specific code) - it's the same
# regardless of what serves the UI, which is why it carried over unchanged from the
# earlier Streamlit build.

import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "database")
DB_PATH = os.path.join(DB_DIR, "researchlens.db")

os.makedirs(DB_DIR, exist_ok=True)

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def init_db():
    """Create all database tables if they don't already exist. Called once on app startup."""
    from models.user import User  # noqa: F401
    from models.project import ResearchProject  # noqa: F401
    from models.paper import Paper  # noqa: F401
    from models.saved_paper import SavedPaper  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations():
    """
    create_all() above only creates tables that don't exist yet - it never adds a new
    column to a table that's already on disk. Since this is a local SQLite prototype
    with no Alembic, we handle the one case that matters (a model gained a column
    after the database file already existed) by hand: check with PRAGMA table_info,
    and ALTER TABLE ADD COLUMN if it's missing. Safe to call every startup - it's a
    no-op once the column is there.
    """
    inspector = inspect(engine)
    if "research_projects" not in inspector.get_table_names():
        return  # create_all() just made it fresh, so it already has every column

    existing_columns = {col["name"] for col in inspector.get_columns("research_projects")}
    if "last_viewed_at" not in existing_columns:
        with engine.connect() as connection:
            connection.execute(text("ALTER TABLE research_projects ADD COLUMN last_viewed_at DATETIME"))
            connection.commit()


def get_session():
    """Return a fresh database session. Remember to close it when you're done with it."""
    return SessionLocal()
