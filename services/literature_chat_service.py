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

import json

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
    exactly what the chat page renders as the running thread. Ordered by id rather
    than created_at, the same tie-breaker edit_and_truncate_message() below relies
    on - the two normally agree, but id is the one guaranteed never to tie between
    a question and the answer that follows it in the same request."""
    return (
        session.query(LiteratureChatMessage)
        .filter(LiteratureChatMessage.project_id == project_id)
        .order_by(LiteratureChatMessage.id.asc())
        .all()
    )


def get_chat_message(session, project_id: int, message_id: int):
    """One message, scoped to the project it's supposed to belong to - so a
    message id can't be edited (see edit_and_truncate_message() below) through a
    URL for a project it doesn't belong to, the same guard models/note.py's
    get_note() applies to a note id."""
    return (
        session.query(LiteratureChatMessage)
        .filter(LiteratureChatMessage.id == message_id, LiteratureChatMessage.project_id == project_id)
        .first()
    )


def get_recent_history_for_prompt(session, project_id: int, before_id: int = None):
    """
    The most recent MAX_HISTORY_MESSAGES_FOR_PROMPT messages, oldest-first, as plain
    {"role", "content"} dicts - what routes/papers_routes.py's ask_literature_stream()
    hands to stream_ask_literature() as conversation context BEFORE the new question
    that triggered this call (which is passed to that function separately, since it
    hasn't been saved to the database yet at the point this is read).

    `before_id`, when given, excludes that message and everything after it - what
    resend_ask_literature_message() uses instead, since an edited question's own
    "history" is whatever came before the ORIGINAL version of that question, never
    including it (it's being replaced, not repeated back to the AI as if it were a
    separate earlier turn).
    """
    query = session.query(LiteratureChatMessage).filter(LiteratureChatMessage.project_id == project_id)
    if before_id is not None:
        query = query.filter(LiteratureChatMessage.id < before_id)
    messages = query.order_by(LiteratureChatMessage.id.desc()).limit(MAX_HISTORY_MESSAGES_FOR_PROMPT).all()
    messages.reverse()
    return [{"role": message.role, "content": message.content} for message in messages]


def add_chat_message(session, project_id: int, role: str, content: str, evidence: list = None) -> LiteratureChatMessage:
    """
    Append one turn (role is "user" or "assistant") to a project's conversation.
    `evidence` (Sprint 5 - see services/evidence_service.py's
    build_multi_paper_evidence()) only ever applies to an "assistant" row - which
    of the project's papers that answer actually drew from, each with a verbatim
    quote and whether it verified. Stored JSON-encoded in the evidence column (a
    Python None stays a database NULL rather than becoming the string "null", so
    get_message_evidence() below can tell "never generated with evidence" apart
    from "generated with zero citations").
    """
    message = LiteratureChatMessage(
        project_id=project_id, role=role, content=content,
        evidence=json.dumps(evidence) if evidence is not None else None,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def get_message_evidence(message: LiteratureChatMessage) -> list:
    """Deserializes one message's evidence column back into the list of
    {"paper_id", "label", "quote", "verified"} dicts add_chat_message() stored -
    an empty list for a "user" row, an old row from before this feature existed,
    or an answer that genuinely cited nothing, so templates can render the same
    way (no evidence chips) in every one of those cases without special-casing."""
    if not message.evidence:
        return []
    try:
        return json.loads(message.evidence)
    except (TypeError, ValueError):
        return []


def edit_and_truncate_message(session, project_id: int, message_id: int, new_content: str) -> LiteratureChatMessage:
    """
    Rewrites one of your own earlier questions and discards everything that came
    after it in the thread (its old answer, and any later questions/answers) - the
    "Edit" + "Resend" action on a user bubble (templates/ask_literature.html,
    static/js/app.js's edit-mode handling). This app's conversation is a single
    linear thread rather than a branching one, so an edited question can't simply
    be appended - its old answer no longer matches the new question, and anything
    asked afterwards may have depended on the very answer that's about to change,
    so the only consistent option is to drop the thread from this point on and let
    a fresh answer (and, if the user asks again, a fresh continuation) replace it.

    Truncation compares by id rather than created_at: a question and the answer it
    triggered are written by two different requests a moment apart, so their
    timestamps are already safely ordered in practice, but id is the one column
    guaranteed to reflect insertion order with no possible tie.
    """
    session.query(LiteratureChatMessage).filter(
        LiteratureChatMessage.project_id == project_id,
        LiteratureChatMessage.id > message_id,
    ).delete()
    message = session.query(LiteratureChatMessage).get(message_id)
    message.content = new_content
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
