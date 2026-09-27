# services/literature_chat_service.py
#
# The "Ask the Literature" feature (Sprint 4): a running Q&A conversation, scoped to
# one project, answered using every paper currently saved to that project (see
# services/openai_service.py's stream_ask_literature()) - unlike Paper Synthesis,
# which lets you hand-pick a subset of papers, Ask the Literature always draws on
# the project's whole saved library, so a new question can be asked about any of
# its papers without re-selecting anything first.
#
# Each turn (a user question, or an AI answer) is its own LiteratureChatMessage row,
# the same "one row per turn" shape models/note.py uses for notes - a conversation
# is inherently a sequence of turns, not a single result to overwrite each time the
# way ResearchProject.synthesis_text is.

from models.literature_chat_message import LiteratureChatMessage

# How many of the most recent messages (user + assistant combined) get sent back to
# the AI as conversation context for a follow-up question - keeps the prompt from
# growing without bound as a conversation gets long, while still letting a
# "what about the second one?"-style follow-up refer back a few turns. Older turns
# stay in the database and still show in the page's own history - this only limits
# what's resent to the AI on the NEXT question (see services/openai_service.py's
# stream_ask_literature(), which caps this further by character count too).
MAX_HISTORY_MESSAGES_FOR_PROMPT = 8


def get_chat_messages_for_project(session, project_id: int):
    """Every turn of this project's Ask the Literature conversation, oldest first -
    exactly what the chat page renders as the running thread."""
    return (
        session.query(LiteratureChatMessage)
        .filter(LiteratureChatMessage.project_id == project_id)
        .order_by(LiteratureChatMessage.created_at.asc())
        .all()
    )


def get_recent_history_for_prompt(session, project_id: int):
    """
    The most recent MAX_HISTORY_MESSAGES_FOR_PROMPT messages, oldest-first, as plain
    {"role", "content"} dicts - what routes/papers_routes.py's ask_literature_stream()
    hands to stream_ask_literature() as conversation context BEFORE the new question
    that triggered this call (which is passed to that function separately, since it
    hasn't been saved to the database yet at the point this is read).
    """
    messages = (
        session.query(LiteratureChatMessage)
        .filter(LiteratureChatMessage.project_id == project_id)
        .order_by(LiteratureChatMessage.created_at.desc())
        .limit(MAX_HISTORY_MESSAGES_FOR_PROMPT)
        .all()
    )
    messages.reverse()
    return [{"role": message.role, "content": message.content} for message in messages]


def add_chat_message(session, project_id: int, role: str, content: str) -> LiteratureChatMessage:
    """Append one turn (role is "user" or "assistant") to a project's conversation."""
    message = LiteratureChatMessage(project_id=project_id, role=role, content=content)
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def clear_chat_history_for_project(session, project_id: int) -> None:
    """Delete every turn of this project's conversation - the "Clear conversation"
    button's action (templates/ask_literature.html), for starting a fresh thread
    rather than letting one grow forever."""
    session.query(LiteratureChatMessage).filter(
        LiteratureChatMessage.project_id == project_id
    ).delete()
    session.commit()
