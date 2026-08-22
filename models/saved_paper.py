# models/saved_paper.py
#
# The join table that links a Paper to a ResearchProject - "this paper has been saved
# to this project's library." A paper can be saved to more than one project without
# being duplicated in the `papers` table.

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, ForeignKey
from services.database_service import Base


class SavedPaper(Base):
    __tablename__ = "saved_papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    saved_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<SavedPaper project_id={self.project_id} paper_id={self.paper_id}>"