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
# expire_on_commit=False: every route in this app follows the same pattern - open a
# session, do some work, close it, THEN pass the objects it loaded to render_template().
# SQLAlchemy's default (expire_on_commit=True) marks an object's attributes as stale
# after any commit() and re-fetches them from the database on next access - which
# raises DetachedInstanceError once the session that would do that fetching is already
# closed. Turning it off keeps the values already loaded in memory instead, which is
# what every template in this app actually needs.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()


def init_db():
    """Create all database tables if they don't already exist. Called once on app startup."""
    from models.user import User  # noqa: F401
    from models.project import ResearchProject  # noqa: F401
    from models.paper import Paper  # noqa: F401
    from models.saved_paper import SavedPaper  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


# Every column a model has gained after its table could already exist on someone's
# disk, keyed by (table, column) -> the SQL type to add it as. Add a new line here
# whenever a model picks up a new column on an existing table - see the loop below.
_ADDED_COLUMNS = [
    ("research_projects", "last_viewed_at", "DATETIME"),
    ("papers", "summary", "TEXT"),
    ("papers", "summary_generated_at", "DATETIME"),
    ("saved_papers", "notes", "TEXT"),
    ("saved_papers", "relevance_analysis", "TEXT"),
    ("saved_papers", "relevance_generated_at", "DATETIME"),
]


def _apply_lightweight_migrations():
    """
    create_all() above only creates tables that don't exist yet - it never adds a new
    column to a table that's already on disk. Since this is a local SQLite prototype
    with no Alembic, we handle the one case that matters (a model gained a column
    after the database file already existed) by hand: check with PRAGMA table_info,
    and ALTER TABLE ADD COLUMN if it's missing. Safe to call every startup - it's a
    no-op once every column is already there.
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    # Snapshot each table's columns once up front, rather than re-inspecting after
    # every ALTER TABLE below - keeps this immune to whether SQLite's driver makes a
    # just-executed, not-yet-committed DDL statement visible to a fresh reflection
    # query on the same connection.
    existing_columns_by_table = {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in table_names
    }

    with engine.connect() as connection:
        for table, column, sql_type in _ADDED_COLUMNS:
            if table not in table_names:
                continue  # create_all() just made it fresh, so it already has every column
            if column not in existing_columns_by_table[table]:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
                existing_columns_by_table[table].add(column)
        connection.commit()


def get_session():
    """Return a fresh database session. Remember to close it when you're done with it."""
    return SessionLocal()
