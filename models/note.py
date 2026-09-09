# models/note.py
#
# One user-written note on one saved paper, within one project. Sprint 3 originally
# gave each saved paper a single free-form notes field (SavedPaper.notes) - this
# replaces that with a list of separate notes per saved paper, each behaving like its
# own small file: its own optional title, its own content, and its own edit history
# (created_at / updated_at), so a paper can carry several distinct notes ("initial
# read", "follow-up after re-reading", "quotes for the lit review", etc.) instead of
# one shared block of text.
#
# A note belongs to exactly one SavedPaper (never directly to a Paper), matching the
# existing rule that notes are inherently about ONE project's relationship to a
# paper - the same paper saved to two different projects can have completely
# different notes on each (see models/saved_paper.py).

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from services.database_service import Base


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    saved_paper_id = Column(Integer, ForeignKey("saved_papers.id"), nullable=False, index=True)
    title = Column(String(200), nullable=True)   # optional - falls back to "Note N" (by position) when blank
    content = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Note id={self.id} saved_paper_id={self.saved_paper_id}>"
