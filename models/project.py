# models/project.py
#
# Defines the "research_projects" table - one row per research project a user creates.
# Matches the "Research Projects" entity from the project plan's database design (section 9).

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from services.database_service import Base


class ResearchProject(Base):
    __tablename__ = "research_projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    research_question = Column(Text, nullable=True)
    research_field = Column(String(120), nullable=True)
    keywords = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Set the first time a user opens this project's detail page, and refreshed on every
    # later visit - this is what powers the dashboard's "Recently viewed" list. Nullable
    # because a brand-new project hasn't been opened yet (it just falls back to
    # created_at for ordering - see get_recent_projects_for_user()).
    last_viewed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<ResearchProject id={self.id} title={self.title!r}>"
