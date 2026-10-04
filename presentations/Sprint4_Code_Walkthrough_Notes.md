# Sprint 4 Study Notes — Code Walkthrough

**Purpose of this document:** a file-by-file, function-by-function walkthrough of the
actual code added in Sprint 4, for personal study / defense prep. Pair this with
`Sprint4_Concepts_and_Features_Notes.md`, which covers the concepts and reasoning — this
document stays close to the code itself: what each function does, what calls it, and
what it returns.

Sprint 4 touched: one new model + table (`LiteratureChatMessage`), new columns on two
existing models (`Paper`, `ResearchProject`), one new service file
(`literature_chat_service.py`), one new service file (`export_service.py`), new
functions in two existing services (`paper_service.py`, `project_service.py`,
`openai_service.py`), a dozen-odd new routes in `routes/papers_routes.py`, and three new
templates (`literature_matrix.html`, `paper_synthesis.html`, `ask_literature.html`) plus
matching JS in `static/js/app.js`.

---

## 1. Data layer: new columns and a new table

### 1.1 `models/paper.py` — four new columns

```python
matrix_methodology  = Column(Text, nullable=True)
matrix_sample        = Column(Text, nullable=True)
matrix_findings       = Column(Text, nullable=True)
matrix_limitations    = Column(Text, nullable=True)
matrix_generated_at   = Column(DateTime, nullable=True)
```

All nullable, all living on `Paper` (not on `SavedPaper`) — see the concepts doc §3.3
for why that placement was chosen. `matrix_generated_at` is stamped on *either* an AI
extraction or a manual edit — it means "last set," not "last AI-generated."

### 1.2 `models/project.py` — three new columns

```python
synthesis_text          = Column(Text, nullable=True)
synthesis_paper_ids     = Column(Text, nullable=True)   # comma-separated ids, e.g. "3,7,12"
synthesis_generated_at  = Column(DateTime, nullable=True)
synthesis_evidence      = Column(Text, nullable=True)   # Sprint 5 - JSON, not Sprint 4 scope
```

A project has exactly **one current synthesis** — regenerating overwrites these columns
in place, it is not versioned/historied.

### 1.3 `models/literature_chat_message.py` — a whole new table

```python
class LiteratureChatMessage(Base):
    __tablename__ = "literature_chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("research_projects.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)   # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    evidence = Column(Text, nullable=True)       # Sprint 5 - not Sprint 4 scope
```

One row per **turn** of the conversation (a question, or an answer) — never one row per
whole conversation. This is the same shape `models/note.py` already used for notes:
append-only, one-row-per-item, rather than a single field that gets overwritten.
`project_id` is indexed since every query against this table filters by it.

### 1.4 How the new columns/table actually get created: `_ADDED_COLUMNS`

`services/database_service.py` has a lightweight, in-code migration mechanism (predates
Sprint 4) — a list of `(table, column, DDL)` tuples checked and applied at startup if
missing, instead of a full migrations framework like Alembic. Sprint 4's new columns
were added to that list; the new table is created automatically because SQLAlchemy's
`Base.metadata.create_all()` (also called at startup) creates any table that doesn't
exist yet for any declared model.

---

## 2. `services/paper_service.py` — new functions

### 2.1 `set_paper_matrix_fields(session, paper, methodology, sample, findings, limitations)`

```python
def set_paper_matrix_fields(session, paper, methodology, sample, findings, limitations):
    paper.matrix_methodology = (methodology or "").strip() or None
    paper.matrix_sample = (sample or "").strip() or None
    paper.matrix_findings = (findings or "").strip() or None
    paper.matrix_limitations = (limitations or "").strip() or None
    paper.matrix_generated_at = datetime.utcnow()
    session.commit()
    session.refresh(paper)
    return paper
```

**What it does:** writes all four Matrix columns in one call, normalizing empty/
whitespace-only input to `None` (so a blank cell reads as "not set" rather than an empty
string). **Who calls it:** both the AI-extraction route (after a successful
`stream_extract_matrix_fields()` run) and the manual-edit route
(`edit_matrix_fields()`) — the exact same function, which is *the* mechanism behind "AI
extraction and manual editing aren't mutually exclusive" (see concepts doc §3.2 step 5).

### 2.2 `build_synthesis_capsule(paper)`

```python
def build_synthesis_capsule(paper) -> str:
    matrix_parts = []
    if paper.matrix_methodology:
        matrix_parts.append(f"Methodology: {paper.matrix_methodology}")
    if paper.matrix_sample:
        matrix_parts.append(f"Sample: {paper.matrix_sample}")
    if paper.matrix_findings:
        matrix_parts.append(f"Findings: {paper.matrix_findings}")
    if paper.matrix_limitations:
        matrix_parts.append(f"Limitations: {paper.matrix_limitations}")
    if matrix_parts:
        return "\n".join(matrix_parts)
    if paper.abstract:
        return f"Abstract: {paper.abstract}"
    if paper.extracted_text:
        return f"Extracted text (excerpt): {paper.extracted_text[:2000]}"
    return "No abstract, extracted text, or matrix fields available for this paper."
```

**What it does:** a pure function (no database session parameter, no I/O) that reduces
one `Paper` object down to a single descriptive string, trying the Matrix fields first,
then the abstract, then a 2,000-character slice of extracted PDF text, then a plain
"nothing available" fallback. **Who calls it:** both `synthesis_stream()` and
`ask_literature_stream()`/`resend_ask_literature_message()` in `papers_routes.py` — the
one function that both Sprint 4 multi-paper features share.

---

## 3. `services/project_service.py` — new functions

### 3.1 `count_projects_with_synthesis_for_user(session, user_id)`

A one-line `COUNT` query (`ResearchProject.synthesis_text.isnot(None)`) that powers a
dashboard stat card — swapped in to replace what used to be a hardcoded `0` placeholder
for an earlier, unbuilt "Research Gaps" feature idea.

### 3.2 `set_project_synthesis(session, project, text, paper_ids, evidence=None)`

```python
def set_project_synthesis(session, project, text, paper_ids, evidence=None):
    project.synthesis_text = text
    project.synthesis_paper_ids = ",".join(str(paper_id) for paper_id in paper_ids)
    project.synthesis_evidence = json.dumps(evidence) if evidence is not None else None
    project.synthesis_generated_at = datetime.utcnow()
    session.commit()
    session.refresh(project)
    return project
```

**What it does:** writes the synthesis text, re-encodes the ordered list of source
paper ids as a comma-separated string, and stamps the generation time. Note the
`evidence` parameter is Sprint 5 scope (evidence tracking didn't exist in Sprint 4) —
Sprint 4's own calls pass nothing for it, so `synthesis_evidence` stays `NULL`. **Who
calls it:** `synthesis_stream()`'s `generate()` closure, exactly once, when the stream's
`done` event arrives.

### 3.3 `delete_project()` / `delete_all_projects_for_user()` — updated, not new

Both existing cascade-delete functions were extended to also delete a project's
`LiteratureChatMessage` rows before deleting the project itself (or, for the bulk
version, for every project being deleted) — otherwise those rows would be left pointing
at a `project_id` that no longer exists.

---

## 4. `services/literature_chat_service.py` — new file

This entire file is new in Sprint 4. Six functions, all fairly small:

### 4.1 `get_chat_messages_for_project(session, project_id)`

Every message for a project, ordered by `id ASC` — the full thread, oldest first, for
rendering the page.

### 4.2 `get_chat_message(session, project_id, message_id)`

One message, filtered by **both** `id` and `project_id` — the same ownership-scoping
pattern `get_note()` uses, so a message id from another project can't be edited through
a crafted URL.

### 4.3 `get_recent_history_for_prompt(session, project_id, before_id=None)`

```python
def get_recent_history_for_prompt(session, project_id, before_id=None):
    query = session.query(LiteratureChatMessage).filter(LiteratureChatMessage.project_id == project_id)
    if before_id is not None:
        query = query.filter(LiteratureChatMessage.id < before_id)
    messages = query.order_by(LiteratureChatMessage.id.desc()).limit(MAX_HISTORY_MESSAGES_FOR_PROMPT).all()
    messages.reverse()
    return [{"role": message.role, "content": message.content} for message in messages]
```

**What it does:** fetches the most recent `MAX_HISTORY_MESSAGES_FOR_PROMPT` (= 8)
messages — ordered `DESC` with a `LIMIT` to get the *most recent* ones efficiently, then
`.reverse()`'d back into chronological order before being handed to the AI call. The
optional `before_id` excludes a message and everything after it; this is what
`resend_ask_literature_message()` uses so an edited question's "history" never includes
the version of itself that's about to be overwritten.

### 4.4 `add_chat_message(session, project_id, role, content, evidence=None)`

Inserts one new row. `evidence` is Sprint 5 scope (`json.dumps(evidence) if evidence is
not None else None` — Sprint 4's own call sites pass nothing, so this column stays
`NULL` for Sprint-4-era rows).

### 4.5 `edit_and_truncate_message(session, project_id, message_id, new_content)`

```python
def edit_and_truncate_message(session, project_id, message_id, new_content):
    session.query(LiteratureChatMessage).filter(
        LiteratureChatMessage.project_id == project_id,
        LiteratureChatMessage.id > message_id,
    ).delete()
    message = session.query(LiteratureChatMessage).get(message_id)
    message.content = new_content
    session.commit()
    session.refresh(message)
    return message
```

**What it does:** a bulk `DELETE` of every message in this project with a higher `id`
than the one being edited, then overwrites that message's own `content` in place. This
is the entire "Edit + Resend" mechanic — see concepts doc §5.5 for the reasoning behind
truncating forward instead of branching.

### 4.6 `clear_chat_history_for_project(session, project_id)`

A one-line bulk delete of every message for a project — "Clear conversation."

---

## 5. `services/openai_service.py` — three new streaming functions

(The file's shared `_stream()` plumbing — the generator that actually talks to
OpenAI's Responses API and yields `{"delta"}`/`{"error"}`/`{"done"}` events — predates
Sprint 4, from Sprint 3. Sprint 4 adds three new callers of it. Note: in the file as it
exists *today*, these functions call `_stream_with_multi_paper_evidence(...)` instead of
`_stream(...)` directly — that wrapper is Sprint 5's evidence-tracking layer. In Sprint
4's own scope, think of it as a thin pass-through to `_stream()`; the evidence-specific
behavior described in the Sprint 5 docs did not exist yet.)

### 5.1 `stream_extract_matrix_fields(title, authors, year, text)`

Builds a system prompt demanding **exactly four** plain-prose paragraphs — Methodology,
Sample, Findings, Limitations, in that order, blank-line separated, no markdown — then
delegates to the shared streaming plumbing. Guards against empty input text up front
(`if not (text or "").strip(): yield {"error": ...}`), the same pattern every other
AI-calling function in this file uses.

### 5.2 `stream_synthesize_papers(project_title, research_question, papers)`

```python
def stream_synthesize_papers(project_title, research_question, papers):
    if len(papers) < 2:
        yield {"error": "Select at least 2 papers to synthesize."}
        return
    system_prompt = (...)          # five-part structure, described in concepts doc §4.2
    papers_block = "\n\n".join(
        f"Paper {i + 1}:\nTitle: {paper['title']}\nAuthors: {paper['authors'] or 'Not specified'}\n"
        f"Year: {paper['year'] if paper['year'] else 'Not specified'}\n{paper['capsule']}"
        for i, paper in enumerate(papers)
    )
    user_content = f"{context_block}Papers:\n\n{papers_block}"
    yield from _stream_with_multi_paper_evidence(system_prompt, user_content, papers)
```

**What it does:** the 2-paper guard (concepts doc §4.3) lives right at the top, before
any prompt is even built. `papers` here is the list of capsule dicts
`synthesis_stream()` built from `build_synthesis_capsule()`. Each paper is rendered into
the prompt as a numbered block (`Paper 1: ... Paper 2: ...`), which is also what the
system prompt's citation instructions point back to ("cite with a standard academic
in-text citation built from its own authors/year given below").

### 5.3 `stream_ask_literature(project_title, research_question, papers, history, question)`

The most involved of the three. Four module-level constants define the per-piece
character budgets discussed in concepts doc §5.4:

```python
MAX_PAPERS_BLOCK_CHARS = 8_000
MAX_HISTORY_BLOCK_CHARS = 4_000
MAX_QUESTION_CHARS = 2_000
ASK_LITERATURE_INPUT_CHARS = MAX_PAPERS_BLOCK_CHARS + MAX_HISTORY_BLOCK_CHARS + MAX_QUESTION_CHARS + 2_000
```

Inside the function, each piece is capped **individually**, in this order:

```python
papers_block = "\n\n".join(...)[:MAX_PAPERS_BLOCK_CHARS]

history_block = ""
if history:
    history_lines = [f"{'Q' if turn['role'] == 'user' else 'A'}: {turn['content']}" for turn in history]
    history_block = ("Conversation so far:\n" + "\n".join(history_lines))[:MAX_HISTORY_BLOCK_CHARS] + "\n\n"

question_block = f"New question: {(question or '').strip()[:MAX_QUESTION_CHARS]}"

user_content = f"{context_block}Papers:\n\n{papers_block}\n\n{history_block}{question_block}"
```

The question is concatenated **last**, after being capped on its own — so no matter how
long the papers block or history ends up, the question text itself is never at risk of
being cut off by a later truncation step. `ASK_LITERATURE_INPUT_CHARS` (the sum of all
three caps, plus a buffer) is passed as this call's `max_input_chars` to the shared
streaming plumbing — comfortably larger than the assembled text could ever be, so that
generic safety-net truncation never actually triggers in practice for this call.

---

## 6. `services/export_service.py` — new file

New in Sprint 4. Builds three downloadable formats of the Literature Matrix, all from
one shared row-builder:

```python
COLUMNS = ["Paper", "Authors", "Year", "Methodology", "Sample", "Findings", "Limitations"]
NOT_EXTRACTED = "Not extracted yet"

def _row_for_paper(paper):
    return [
        paper.title,
        paper.authors or "Unknown authors",
        paper.year or "",
        paper.matrix_methodology or NOT_EXTRACTED,
        paper.matrix_sample or NOT_EXTRACTED,
        paper.matrix_findings or NOT_EXTRACTED,
        paper.matrix_limitations or NOT_EXTRACTED,
    ]
```

`build_matrix_excel()`, `build_matrix_pdf()`, and `build_matrix_docx()` each loop over
the saved papers and call `_row_for_paper()` once per paper, then format that same list
of values into their respective library's API:

- **Excel** (`openpyxl`): a `Workbook`/`Worksheet`, a merged title row, a styled header
  row (navy fill, white bold text), `Alignment(wrap_text=True)` on every data cell,
  fixed column widths, and `freeze_panes` so the header stays visible while scrolling.
- **PDF** (`reportlab`): a `SimpleDocTemplate` with a landscape `letter` page, a
  `Table` built from `Paragraph` objects (not bare strings — `Paragraph` wraps long
  text within its column, which plain strings in a `Table` cell don't). Note the
  `_rl_text()` helper, which **XML-escapes** every value before handing it to
  `Paragraph` — necessary because reportlab's `Paragraph` parses its input as a small
  markup language, so an AI-extracted or hand-typed value containing a raw `&`, `<`, or
  `>` would otherwise throw a parse error.
- **Word** (`python-docx`): a landscape `Document`, a `Table Grid`-styled table, and two
  low-level XML helpers — `_shade_cell()` (sets a cell's background color by directly
  appending a `<w:shd>` element, since `python-docx`'s high-level API has no
  cell-shading method) and `_mark_repeat_header()` (flags the header row to repeat on
  every page a table spans, via a raw `<w:tblHeader>` element).

`export_filename(project, extension)` builds a safe download filename by slugifying the
project's title (`re.sub(r"[^A-Za-z0-9]+", "_", text)`).

---

## 7. `routes/papers_routes.py` — new/changed routes

All routes below follow the same two patterns already established in earlier sprints:
`_require_login()` first, then `_get_owned_project_or_404()` (or equivalent) so a
project/paper that doesn't belong to the logged-in user 404s rather than leaking
existence. New in Sprint 4:

| Route | Method | What it does |
|---|---|---|
| `/projects/<id>/matrix` | GET | Renders `literature_matrix.html` with the project's saved papers |
| `/projects/<id>/matrix/export.xlsx` | GET | Streams an Excel download via `export_service.build_matrix_excel()` |
| `/projects/<id>/matrix/export.docx` | GET | Same, Word, via `build_matrix_docx()` |
| `/projects/<id>/matrix/export.pdf` | GET | Same, PDF, via `build_matrix_pdf()` |
| `/projects/<id>/papers/<id>/matrix/edit` | POST | Manual edit path — calls `set_paper_matrix_fields()` directly, no AI involved |
| `/synthesis` | GET | Entry point from the sidebar; redirects straight into the (only) project's synthesis page, or asks which project if there's more than one |
| `/projects/<id>/synthesis` | GET | Renders `paper_synthesis.html`; resolves `synthesis_paper_ids` back into actual `Paper` objects for the "Based on: ..." line |
| `/projects/<id>/synthesis/stream` | POST | Streams a new synthesis; re-validates submitted `paper_ids`, calls `stream_synthesize_papers()`, persists via `set_project_synthesis()` on `done` |
| `/ask-literature` | GET | Entry point from the sidebar, same single/choose pattern as `/synthesis` |
| `/projects/<id>/ask-literature` | GET | Renders `ask_literature.html` with the full message history |
| `/projects/<id>/ask-literature/stream` | POST | Streams a new question's answer — persists the **question** immediately (before streaming starts), then the **answer** once the stream completes |
| `/projects/<id>/ask-literature/messages/<id>/resend` | POST | "Edit + Resend" — calls `edit_and_truncate_message()`, then streams a fresh answer the same way |
| `/projects/<id>/ask-literature/clear` | POST | Calls `clear_chat_history_for_project()`, flashes a confirmation, redirects back |

### 7.1 `synthesis_stream()` — the id re-validation pattern

```python
requested_ids = [int(pid) for pid in request.form.getlist("paper_ids") if pid.strip().isdigit()]
...
seen = set()
ordered_ids = []
for pid in requested_ids:
    if pid in papers_by_id and pid not in seen:
        seen.add(pid)
        ordered_ids.append(pid)
```

`papers_by_id` here is built from `get_saved_papers_for_project(db_session,
project_id)` — i.e. **this project's own saved papers**, queried server-side,
independent of whatever the client submitted. Any submitted id not in that dict is
silently dropped. This is what stops a tampered form from referencing a paper id that
belongs to a different project (or a different user entirely).

### 7.2 `ask_literature_stream()` — persisting the question before streaming starts

```python
question_message = add_chat_message(db_session, project_id, "user", question)
question_id = question_message.id
...
def generate():
    yield json.dumps({"question_id": question_id}) + "\n"
    for event in stream_ask_literature(...):
        if event.get("done"):
            answer_message = add_chat_message(write_session, project_id, "assistant", event["text"], ...)
            event = dict(event, answer_id=answer_message.id)
        yield json.dumps(event) + "\n"
```

**Why persist the question before the AI call even starts, rather than saving both
question and answer together once generation finishes** (which is what Paper
Synthesis does)? If generation fails or the connection drops partway, the user's
question is never lost — it's already a row in the database the moment the request
was accepted, exactly like a message you've sent in a real chat app stays visible
regardless of whether the other side ever replies. The first line streamed back is
always `{"question_id": ...}`, which the JS uses to tag that question's chat bubble
with its real database id immediately — so Edit + Resend works on it without first
needing a page reload.

### 7.3 Two independent database sessions per streamed request

Notice both `synthesis_stream()` and `ask_literature_stream()` open **two** separate
`get_session()` calls: one before `generate()` (to read the project/papers and, for Ask
the Literature, to save the question), and a second one *inside* `generate()`'s loop,
opened only once the `done` event arrives (to save the result). This split exists
because `generate()` is a generator consumed lazily by Flask while streaming the HTTP
response — the first session is closed (via its `finally` block) before the response
even starts streaming, so a second, fresh session is opened only when there's
something new to write, rather than holding one database connection open for the
entire, potentially slow, duration of the AI generation.

---

## 8. Frontend — `static/js/app.js` and the three new templates

Not line-by-line here (the JS is generic/shared, not duplicated per feature), but worth
knowing the shape:

- **One shared streaming handler**, keyed off a `[data-stream-url]` attribute, reused by
  AI Summary, Relevance Analysis, Matrix extraction, *and* Paper Synthesis. It opens a
  `fetch()` to whatever URL the triggering button declares, reads the response body as
  NDJSON line-by-line, and appends each `delta` to the target element(s) — for Matrix
  extraction specifically, `data-targets` on the button tells the handler which four DOM
  elements to split the streamed paragraphs into as blank lines are encountered.
- **A separate chat-specific handler**, keyed off `[data-chat-form]`, for Ask the
  Literature — structurally similar (same NDJSON-over-fetch pattern) but needs extra
  logic a generic streaming target doesn't: appending a brand-new bubble to the thread
  rather than filling in an existing one, tagging that bubble with the `question_id`/
  `answer_id` the server sends back, and wiring up each bubble's hover-reveal Edit/Copy
  icons.
- **`literature_matrix.html`** renders the table server-side from `papers`, with each
  row's "Extract with AI" button carrying `data-stream-url` pointed at that paper's
  extraction endpoint and `data-targets` naming its four cells.
- **`paper_synthesis.html`** renders one checkbox per saved paper (`name="paper_ids"`,
  `value="<paper.id>"`) plus a "Generate Synthesis" button whose `data-stream-url`
  points at `/projects/<id>/synthesis/stream`; the generic handler collects every
  checked box's value as repeated `paper_ids=` form fields when it POSTs.
- **`ask_literature.html`** renders the full message history server-side
  (`messages` from `get_chat_messages_for_project()`), then the chat-specific JS handler
  takes over for anything added during the current page visit (new questions, edits,
  clears) without a full reload.

---

## 9. Quick map: "if I'm asked to find X, where does it live?"

| If asked about... | Look in... |
|---|---|
| How the Matrix's 4 fields get extracted | `openai_service.stream_extract_matrix_fields()` |
| How a manual Matrix edit is saved | `paper_service.set_paper_matrix_fields()` + `routes/papers_routes.py`'s `edit_matrix_fields()` |
| How Excel/PDF/Word exports stay consistent | `export_service._row_for_paper()` |
| How a paper gets summarized into one line for Synthesis/Ask | `paper_service.build_synthesis_capsule()` |
| The 2-paper synthesis guard | `openai_service.stream_synthesize_papers()`, top of the function |
| How synthesis is saved with its source papers | `project_service.set_project_synthesis()` |
| How the chat's prompt is assembled/budgeted | `openai_service.stream_ask_literature()` |
| How Edit + Resend truncates the thread | `literature_chat_service.edit_and_truncate_message()` |
| How only the last 8 turns get resent to the model | `literature_chat_service.get_recent_history_for_prompt()` |
| Where a submitted paper id gets re-validated | `routes/papers_routes.py`'s `synthesis_stream()`, the `ordered_ids` loop |
