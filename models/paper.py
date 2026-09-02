# models/paper.py
#
# Defines the "papers" table. A Paper can come from two places (see `source`):
#   - "semantic_scholar": found through the academic search, external_id holds
#     Semantic Scholar's own paperId so we never save the same paper twice.
#   - "upload": a PDF the user uploaded directly from their computer. file_path points
#     at the saved file in uploads/, and extracted_text holds the text PyMuPDF pulled
#     out of it - Sprint 3's AI analysis reads from extracted_text (or abstract, for
#     search-found papers) rather than needing to touch the PDF again.
#
# `summary` holds the Sprint 3 AI-generated summary (see services/openai_service.py's
# summarize_paper()). It lives here on Paper rather than on SavedPaper because a
# paper's summary doesn't depend on which project it's saved to - unlike relevance
# analysis and notes (see models/saved_paper.py), which are inherently project-
# specific and so live on the project<->paper link instead.

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from services.database_service import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    authors = Column(String(500), nullable=True)
    year = Column(Integer, nullable=True)
    abstract = Column(Text, nullable=True)
    doi = Column(String(255), nullable=True)
    url = Column(String(500), nullable=True)
    source = Column(String(50), nullable=False, default="manual")  # "semantic_scholar" or "upload"
    external_id = Column(String(255), nullable=True, index=True)   # Semantic Scholar's paperId, if applicable
    file_path = Column(String(500), nullable=True)                 # path to the saved PDF, if uploaded
    extracted_text = Column(Text, nullable=True)                   # text pulled from the PDF, if uploaded
    summary = Column(Text, nullable=True)                          # AI-generated summary (Sprint 3), NULL until generated
    summary_generated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Paper id={self.id} title={self.title!r}>"