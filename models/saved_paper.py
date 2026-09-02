# models/saved_paper.py
#
# The join table that links a Paper to a ResearchProject - "this paper has been saved
# to this project's library." A paper can be saved to more than one project without
# being duplicated in the `papers` table.
#
# `notes` and `relevance_analysis` also live here, rather than on Paper, because both
# are inherently about ONE project's relationship to this paper: the same paper saved
# to two different projects can have completely different notes, and a completely
# different relevance judgement (each project has its own research question - see
# services/openai_service.py's analyze_relevance()).

from datetime import datetime
from sqlalchemy import Column, Integer, DateTime, Text, ForeignKey
from services.database_service import Base


class SavedPaper(Base):
    __tablename__ = "saved_papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False)
    paper_id = Column(Integer, ForeignKey("papers.id"), nullable=False)
    saved_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)                    # free-form user notes on this paper, in this project
    relevance_analysis = Column(Text, nullable=True)       # AI-generated relevance analysis (Sprint 3), NULL until generated
    relevance_generated_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<SavedPaper project_id={self.project_id} paper_id={self.paper_id}>"