# Ask the Literature — Sprint 4 Defense Notes

*A plain-English guide for the team. No coding background needed.*

---

## 1. What this feature actually is, in one sentence

A running, ChatGPT-style conversation where you can ask questions about
every paper you've saved to a project, get answers grounded in those papers
specifically, and keep asking follow-up questions in the same thread.

---

## 2. The problem we were solving (the "why")

By this point the app could summarize one paper, and combine several
hand-picked papers into one synthesis. But a user often doesn't want a
formal written piece — they want to *ask something specific*, like "which of
these papers used a survey?" or "do any of them disagree on outcomes?" and
get a direct answer, then ask a follow-up based on that answer.

That's a different shape of problem from Synthesis: it needs to (1) use the
**whole library** automatically, not a hand-picked subset, (2) remember
what was already asked and answered so far, and (3) let someone fix a badly
worded question without losing the whole conversation.

---

## 3. How we decided to build it (the design decisions)

**Decision 1 — Always answer from every saved paper, not a chosen subset.**
Synthesis is deliberate: "compare exactly these papers." Ask the Literature
is exploratory: the user doesn't want to re-tick checkboxes before every
single question. So we made a conscious choice that this feature always
pulls in every paper currently saved to the project, automatically.

**Decision 2 — Store the conversation as one row per message, not one
blob of text.** We could have saved an entire conversation as one long
string that keeps getting appended to. Instead, every single question and
every single answer gets its own row in the database, in order. This is the
same pattern a real chat app uses, and it's what makes two more decisions
below possible at all.

**Decision 3 — Save the user's question immediately, before waiting for the
AI to answer.** If we waited until the AI finished to save anything (like
Paper Synthesis does), a dropped connection or a failed AI request would
lose the user's question entirely — frustrating, since they already typed
it. So the question is saved to the database the instant it's submitted,
*before* we even start talking to the AI. The answer is saved separately,
once it's ready.

**Decision 4 — Let someone edit a question and get a fresh answer, instead
of just adding a correction underneath.** If your second question was badly
worded, the AI's answer to it (and anything you asked afterward, which may
have leaned on that answer) is now out of date too. So "Edit" doesn't just
add a new message — it rewinds the conversation back to right before that
question, as if it had been typed correctly the first time.

**Decision 5 — Don't resend the entire conversation history to the AI every
time.** A long-running chat could grow very large. Re-sending the whole
thing on every single question would get slower and more expensive the
longer the conversation went on. So we only send the AI the most recent
slice of the conversation (the last 8 turns) — enough for it to understand
context like "what did you mean by 'it'?", without the cost growing forever.

---

## 4. The actual code, explained like you've never coded before

### a) Remembering only the recent part of the conversation

(`services/literature_chat_service.py` → `get_recent_history_for_prompt`)

```python
def get_recent_history_for_prompt(session, project_id, before_id=None):
    query = session.query(LiteratureChatMessage).filter(LiteratureChatMessage.project_id == project_id)
    if before_id is not None:
        query = query.filter(LiteratureChatMessage.id < before_id)
    messages = query.order_by(LiteratureChatMessage.id.desc()).limit(MAX_HISTORY_MESSAGES_FOR_PROMPT).all()
    messages.reverse()
    return [{"role": message.role, "content": message.content} for message in messages]
```

**In plain words:** think of every message in the chat as a numbered sticky
note on a wall. This code says: "grab this project's sticky notes, sort them
newest-first, and take only the most recent 8." Then `.reverse()` flips
them back into the normal oldest-to-newest reading order, because that's how
a conversation actually makes sense to read. The optional `before_id` part
is for editing a question — more on that in (c) below.

### b) Keeping the new question safe from the moment it's typed

(`routes/papers_routes.py` → `ask_literature_stream`)

```python
question_message = add_chat_message(db_session, project_id, "user", question)
question_id = question_message.id
...
def generate():
    yield json.dumps({"question_id": question_id}) + "\n"
    for event in stream_ask_literature(...):
        if event.get("done"):
            answer_message = add_chat_message(write_session, project_id, "assistant", event["text"], ...)
```

**In plain words:** the very first thing this does — before the AI has even
started "typing" an answer — is save the question to the database. Only
after that does it start streaming the AI's answer back to the screen, and
only once the AI is fully finished does it save the answer as its own
separate message. This order matters: it's exactly like sending a text
message — your message shows up and stays sent, whether or not the other
person replies right away or at all.

### c) "Edit and resend" — rewinding the conversation cleanly

(`services/literature_chat_service.py` → `edit_and_truncate_message`)

```python
def edit_and_truncate_message(session, project_id, message_id, new_content):
    session.query(LiteratureChatMessage).filter(
        LiteratureChatMessage.project_id == project_id,
        LiteratureChatMessage.id > message_id,
    ).delete()
    message = session.query(LiteratureChatMessage).get(message_id)
    message.content = new_content
    session.commit()
    return message
```

**In plain words:** imagine the conversation as a numbered list of sticky
notes again. This says: "delete every sticky note numbered *after* the one
being edited" (its old answer, and anything asked afterward) — "then rewrite
that one sticky note's text." The conversation now reads exactly as if the
corrected question had been the real one from the start, with a brand-new
answer generated right after it.

### d) Keeping the question safe from being cut off, even in a long chat

(`services/openai_service.py` → `stream_ask_literature`)

```python
MAX_PAPERS_BLOCK_CHARS = 8_000
MAX_HISTORY_BLOCK_CHARS = 4_000
MAX_QUESTION_CHARS = 2_000

papers_block = (...)[:MAX_PAPERS_BLOCK_CHARS]
history_block = (...)[:MAX_HISTORY_BLOCK_CHARS]
question_block = f"New question: {(question or '').strip()[:MAX_QUESTION_CHARS]}"
user_content = f"{context_block}Papers:\n\n{papers_block}\n\n{history_block}{question_block}"
```

**In plain words:** everything we send the AI has a size limit overall, the
same way a text message or a form field has a character limit. If we just
let the whole thing grow and trimmed it from the end when it got too long,
we could accidentally cut off the user's actual question — the most
important part! So instead, each piece (the papers, the past conversation,
the new question) is trimmed to its **own** separate limit *before* being
stuck together, with the question always placed last. That way the question
itself is essentially guaranteed to always make it through in full, no
matter how much came before it.

---

## 5. How it's implemented — the full journey, step by step

1. User opens Ask the Literature for a project and sees the full
   conversation so far (loaded from the database, oldest to newest).
2. User types a new question and hits send.
3. The server immediately saves the question as its own message (section
   4b) and sends back its ID right away — so the page can show it in the
   chat instantly.
4. The server gathers every paper currently saved to the project (no
   checkboxes needed), plus the last 8 turns of conversation (section 4a),
   plus the new question, with each piece kept within its own size limit
   (section 4d).
5. The AI streams its answer live, with its hidden evidence block (see the
   Evidence Tracking note).
6. Once finished, the answer is saved as its own message, linked to this
   same conversation.
7. If the user later clicks "Edit" on an earlier question: the thread from
   that point onward is deleted (section 4c), the question's text is
   updated, and a brand new answer is generated for it — exactly like
   editing a message in a modern chat app.

---

## 6. Why this works well for our project

- It matches how people naturally want to explore a pile of saved research:
  ask something, see the answer, ask a follow-up — not re-select papers
  every single time.
- Saving the question immediately means a user's effort (typing a good
  question) is never silently lost to a network hiccup or a failed AI call.
- Only sending the AI the recent slice of conversation keeps answers fast
  and keeps costs predictable even in a long-running chat.
- Edit-and-resend keeps the thread trustworthy — there's never a mismatched
  answer sitting under a question that was later changed.

---

## 7. Questions people might ask us, and simple answers

**Q: What happens if the AI takes a while or the connection drops after I
ask a question?**
A: The question is already saved the moment it's submitted — before the AI
is even asked anything — so it's never lost, even if the answer fails to
come back.

**Q: Why can't I choose which papers to ask about, like I can in
Synthesis?**
A: By design — this feature is meant for quickly exploring your whole
saved library without re-selecting papers before every question. If you
want a focused comparison of a specific few papers, that's what Paper
Synthesis is for.

**Q: What happens to the AI's old answer when I edit my question?**
A: It's deleted, along with anything asked after it, and replaced with a
fresh answer to the corrected question — the same way editing a message in
a modern chat app works.

**Q: Does the AI "remember" the whole conversation forever?**
A: It only sees the most recent 8 turns when answering. This keeps answers
fast and the cost of asking a question roughly the same, whether it's your
first question or your fiftieth.

**Q: Could editing an old question accidentally delete something I want to
keep?**
A: Only the messages that came strictly after the one being edited are
removed — editing your very first question clears the whole thread that
followed it, which is intentional, since everything after it was a response
to the version being replaced.

**Q: Why not just store the whole conversation as one big block of text?**
A: Storing one row per message is what makes editing, resending, and
loading only the recent history possible at all — a single growing block of
text can't be selectively trimmed or corrected the same way.

**Q: Can the AI answer using a paper I haven't saved to this project?**
A: No — it's only ever given this project's own saved papers as source
material, and is explicitly told never to use outside knowledge or discuss
a paper that isn't listed.
