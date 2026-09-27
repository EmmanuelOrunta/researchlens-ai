# models/literature_chat_message.py
#
# One turn of the "Ask the Literature" conversation (Sprint 4) for one project -
# either the user's own question ("user") or the AI's answer ("assistant"). Stored
# per project (not per paper) because Ask the Literature always answers using EVERY
# paper currently saved to the project together, the same "whole library" scope
# Paper Synthesis's "select all" option covers, but without needing a hand-picked
# subset - see services/openai_service.py's stream_ask_literature() and
# routes/papers_routes.py's ask_literature_stream().
#
# Kept as a running history of separate rows (like models/note.py's one-row-per-note
# shape) rather than a single overwritten text field (like ResearchProject's
# synthesis_text), because a conversation is inherently a sequence of turns, not one
# current result to replace each time.

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from services.database_service import Base


class LiteratureChatMessage(Base):
    __tablename__ = "literature_chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<LiteratureChatMessage id={self.id} project_id={self.project_id} role={self.role!r}>"
