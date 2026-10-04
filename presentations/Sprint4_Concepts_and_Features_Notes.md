# Sprint 4 Study Notes — Concepts, Features & Thought Process

**Purpose of this document:** personal study / defense-prep notes for Sprint 4 of
ResearchLens AI ("Research Intelligence"). It explains *what* was built, the
*concepts* underneath each piece, *how* each feature actually works end-to-end, the
*technologies* used and why those specific ones, and the *reasoning* behind the design
choices — including the trade-offs considered and the alternatives that were rejected.
Where useful, it also flags a question you might reasonably get asked and how to
answer it.

A companion document, `Sprint4_Code_Walkthrough_Notes.md`, walks through the actual new
code file by file. This document stays one level up — concepts and reasoning, not line
references.

---

## 1. What Sprint 4 actually is, in one sentence

Sprint 4 took the app from analysing **one paper at a time** (Sprint 3's AI Summary and
Relevance Analysis) to reasoning **across a whole saved library at once**, through three
features: the **Literature Matrix** (structured comparison), **Paper Synthesis**
(narrative synthesis across a chosen set of papers), and **Ask the Literature**
(open-ended, conversational Q&A grounded in a project's whole saved library).

**Why this framing matters if asked "what's the big idea of Sprint 4":** a literature
review isn't just six one-paragraph summaries sitting next to each other — it requires
*comparing* sources, *synthesizing* them into an argument, and being able to *interrogate*
them. Sprint 3 could not do any of those three things because every one of its AI calls
was scoped to exactly one paper. Sprint 4 is the sprint where the app's AI stopped being
single-paper and became library-aware.

---

## 2. Core concepts that show up in all three features

These ideas repeat across all three features, so understanding them once pays off three
times.

### 2.1 Streaming responses (the "typing" effect)

Every AI feature in this app — not just Sprint 4's — streams its answer back token by
token rather than making the user wait for the whole response and then showing it all
at once. This is implemented with OpenAI's **Responses API** in streaming mode
(`client.responses.stream(...)`), consumed server-side as an iterator of events, and
forwarded to the browser as **newline-delimited JSON (NDJSON)** — one JSON object per
line, each line a complete event:

- `{"delta": "..."}` — one small chunk of generated text, as it's produced
- `{"error": "..."}` — something went wrong; nothing should be saved to the database
- `{"done": true, "text": "<full text>"}` — generation finished; this is the moment a
  route persists the result

The browser reads this with `fetch()` and a `ReadableStream` reader, appending each
`delta` to the page as it arrives — the same mechanic that makes ChatGPT's own answers
look like they're being typed live.

**Why stream at all, instead of just waiting for one response?** Two reasons: (1) UX —
a multi-paragraph synthesis can take several seconds to generate; watching it appear
live feels fast even though the total time is the same, where a blank screen for the
same duration feels broken. (2) It's the same mental model the user already has from
using ChatGPT/Claude directly, so it needs no explanation in the UI.

**Why NDJSON instead of, say, Server-Sent Events (SSE)?** NDJSON over a plain streamed
HTTP response is simpler to implement on both ends — no special `EventSource` client API
or `text/event-stream` framing rules, just split on newlines and `JSON.parse()` each
line. For a project this size, that simplicity outweighs SSE's reconnection/retry
features, which this app doesn't need (a failed stream just shows an error and the user
retries manually).

### 2.2 System-prompt-enforced structure (the "exactly N paragraphs" pattern)

Three of Sprint 4's calls (matrix extraction, synthesis, and — carried over from Sprint
3 — the paper summary) all use the same trick: the **system prompt explicitly dictates
the exact output shape** — "produce EXACTLY four paragraphs, in this order, separated by
a blank line, no markdown, no headings" — rather than asking the model for something
free-form and hoping it can be parsed afterwards.

**Why this matters conceptually:** an LLM's raw text output is not structured data.
Without a hard constraint, the model might add a heading, use bullet points one time and
prose the next, or merge two conceptual sections into one paragraph — any of which would
break a simple "split on blank line" parser. By making the *shape* of the output part of
the prompt contract itself, parsing becomes a trivial string `split("\n\n")` on the
server/client side instead of needing a second AI call or a fragile regex to extract
structure. This is a deliberate, cheap alternative to asking the model for JSON function
tool-calls — intentionally simpler for a plain-prose field.

**Likely question: "Why not just ask the model to return JSON?"** Possible, but for this
app's four- and six-paragraph fields, forcing JSON would add escaping/parsing complexity
for no real benefit — the paragraphs themselves need to render as plain prose in the UI
either way, and a broken JSON parse is a harder failure mode to recover from mid-stream
than a missing blank line.

### 2.3 The "capsule" pattern — one compact description per paper

Both Paper Synthesis and Ask the Literature need to hand the model a description of
*several* papers at once inside a single prompt, so each paper is boiled down to a
**capsule**: title, authors, year, and a `capsule` string. `build_synthesis_capsule()`
(in `paper_service.py`) builds that capsule with a clear priority order:

1. If the Literature Matrix has already been generated for this paper, use its four
   distilled fields (Methodology/Sample/Findings/Limitations) — already concise and
   already structured for comparison.
2. Otherwise, fall back to the paper's abstract.
3. Otherwise, fall back to the first 2,000 characters of any extracted PDF text.
4. Otherwise, say plainly that nothing is available.

**Why this fallback order, and why reuse the Matrix fields at all?** The Matrix fields
exist *specifically* to make one paper easy to compare against others — reusing them
means Paper Synthesis and Ask the Literature benefit "for free" from any Matrix
extraction a user has already run, instead of re-deriving a comparison summary from
scratch. It also means a paper's capsule gets *better* over time without any new code —
the moment someone extracts its Matrix fields, every future synthesis or chat answer
about that paper automatically uses the richer, more structured description.

### 2.4 Grounding and citation discipline in the system prompt

All three AI-reasoning features (summary, synthesis, ask) instruct the model to **cite
by author/year, using only information given in the prompt**, and to say plainly when
there isn't enough information rather than guessing. This is a prompt-engineering
decision, not a code-level enforcement (Sprint 4 does not verify these citations against
source text — that came one sprint later, as evidence tracking in Sprint 5). Still, it's
worth understanding as the conceptual seed of Sprint 5's evidence tracking: Sprint 4
established the *convention* of citation ("Huang and Lee (2025)..."), and Sprint 5 added
the *verification* layer on top of that convention.

---

## 3. Feature 1 — Literature Matrix

### 3.1 What it is

A structured comparison table: one row per paper currently saved to a project, four
fixed columns — **Methodology, Sample, Findings, Limitations**. Each cell can be filled
in by AI extraction or typed by hand, and the table can be exported as an Excel
workbook, a PDF, or a Word document.

### 3.2 How it works, end to end

1. The page (`literature_matrix.html`) lists every paper saved to the project, with its
   four cells either populated or showing "Not extracted yet."
2. Clicking **Extract with AI** on a row calls
   `openai_service.stream_extract_matrix_fields(title, authors, year, text)`, which
   streams back exactly four plain-prose paragraphs (same "exactly N, blank-line
   separated, no markdown" contract described in §2.2).
3. The client-side JS splits the streamed text on blank lines into the four target
   cells as it arrives.
4. Once the stream reports `done`, the route calls
   `paper_service.set_paper_matrix_fields(session, paper, methodology, sample,
   findings, limitations)`, which writes all four columns and stamps
   `matrix_generated_at`.
5. A user can also just type into any cell by hand — `routes/papers_routes.py`'s
   `edit_matrix_fields()` calls the *exact same* `set_paper_matrix_fields()` function.
   There is no separate "AI value" vs. "manual value" — once saved, a cell's value is a
   cell's value, regardless of where it came from.
6. Exporting calls one of three routes (`export_matrix_excel`/`_docx`/`_pdf`), each of
   which calls `services/export_service.py`, which reads **every paper's row through
   one shared helper, `_row_for_paper()`**, then feeds that same row data into an
   openpyxl workbook, a reportlab PDF, or a python-docx document respectively.

### 3.3 Where the data actually lives — and why that matters

The four Matrix columns (`matrix_methodology`, `matrix_sample`, `matrix_findings`,
`matrix_limitations`) are columns on the **`Paper`** model, *not* on the
project-to-paper join table (`SavedPaper`). This is a deliberate modeling decision:

- A paper's methodology doesn't change depending on which project happened to save it —
  it's a property of the paper itself.
- Only *which papers appear in a given project's matrix* is project-scoped (determined
  by which papers are saved to that project).
- The practical payoff: if the same paper is saved to two different projects, extracting
  its Matrix fields once means **both** projects' matrices show the populated row — no
  duplicate AI calls, no duplicate storage, and no risk of the two projects' matrices
  disagreeing about the same paper's methodology.

**Likely question: "What if I want different notes on the same paper in two different
projects?"** That's exactly what the *multi-note* system (Sprint 3) is for — notes are
scoped to the `SavedPaper` join row, i.e. per-project. The Matrix fields are
deliberately the opposite: shared, because they describe the paper's own methodology,
not a user's project-specific commentary on it.

### 3.4 Technologies used, and why

| Piece | Technology | Why this one |
|---|---|---|
| AI extraction | OpenAI Responses API (streaming) | Same client/pattern as every other AI feature — one dependency, one calling convention |
| Excel export | `openpyxl` | Pure-Python, no external binary dependency, good styling API (fills, fonts, column widths, freeze panes) |
| PDF export | `reportlab` | Mature, well-documented `Platypus` layout engine (`Table`/`Paragraph`) good at wrapping long text into table cells, which raw string concatenation can't do |
| Word export | `python-docx` | The standard Python library for `.docx`; needed low-level XML access (`OxmlElement`) for cell shading and repeating header rows, since the high-level API doesn't expose those |

**Why export to three formats instead of one?** Different downstream uses: Excel for
further filtering/sorting, Word for pasting into an actual literature review document,
PDF for sharing a fixed, print-ready snapshot. Academic workflows commonly need at least
two of these, so building all three from one shared data function was not much more work
than building one — the expensive part (fetching papers and building rows) is identical,
and the formatting code per-library is isolated per function.

---

## 4. Feature 2 — Paper Synthesis

### 4.1 What it is

Pick any two or more papers saved to a project; get back a single, flowing, 5–8
paragraph piece of academic prose that *synthesizes* them together — not a summary per
paper, one connected narrative, the way a literature review's own "Synthesis Review"
section reads.

### 4.2 How it works, end to end

1. `paper_synthesis.html` lists every saved paper as a checkbox; the user selects two or
   more and clicks **Generate Synthesis**.
2. The form POSTs the checked `paper_ids` to `/projects/<id>/synthesis/stream`.
3. The route (`synthesis_stream()`) takes the submitted ids, **re-validates them against
   this project's own saved papers server-side** (never trusting the client's list at
   face value), and de-duplicates them while preserving the order they were submitted
   in.
4. For each validated paper, it builds a capsule dict (`{id, title, authors, year,
   capsule}`) using `build_synthesis_capsule()` (§2.3).
5. `openai_service.stream_synthesize_papers(project_title, research_question, papers)`
   streams back the synthesis text, built from a system prompt that lays out a specific
   five-part shape: open on the shared theme → compare specific papers by name → name
   what they collectively rely on and what limitations recur → critique the body of work
   as a whole → close on what the literature establishes (and how it relates to the
   project, if a research question was given).
6. On `done`, `project_service.set_project_synthesis(session, project, text, paper_ids,
   evidence)` stores the text **and** the exact ordered list of paper ids it was
   generated from (as a comma-separated string on `ResearchProject.synthesis_paper_ids`)
   — so reopening the page later shows exactly which papers the *current* synthesis is
   "Based on," with the right boxes still checked.

### 4.3 The 2-paper minimum — a deliberate guard, not an oversight

`stream_synthesize_papers()` refuses outright if fewer than two papers are selected,
returning an explicit error ("Select at least 2 papers to synthesize") rather than
quietly generating something. **Why not just let it degrade gracefully to a
single-paper summary?** Because that result would *look* like a synthesis (same page,
same styling) while actually just being a one-paper restatement — misleading rather than
helpful. Making the precondition explicit and visible is safer than a silent fallback
that produces a technically-valid but conceptually wrong result.

### 4.4 Technologies and reasoning

- **Same OpenAI Responses API streaming pattern** as every other AI feature — no new
  client dependency.
- **NDJSON streaming route**, same shape as Literature Matrix extraction — this is a
  reused pattern, not a new mechanism per feature.
- **Server-side re-validation of submitted ids** is a basic but important security habit:
  the route never trusts that a submitted `paper_id` actually belongs to *this* project
  (or even to this user) just because the client sent it — it's checked against
  `get_saved_papers_for_project()`'s own result before being used for anything.

**Likely question: "Why store `synthesis_paper_ids` as a comma-separated string instead
of a real join table?"** A fair trade-off to name directly if asked: a dedicated join
table (`SynthesisPaper`, analogous to `SavedPaper`) would be the "more normalized"
answer, and would support querying "which syntheses include paper X" directly. The
comma-separated string was chosen because a project has **exactly one current
synthesis** at a time (regenerating overwrites the old one, it isn't versioned), so the
relationship is simple enough that a derived table felt like unnecessary schema
overhead for what's really just one list of ids tied to one row. If the project later
needed synthesis *history* (multiple past syntheses per project), a real table would
become the right call.

---

## 5. Feature 3 — Ask the Literature

### 5.1 What it is

A persistent, ChatGPT-style conversation, scoped to one project, where every question is
answered using **every paper currently saved to that project** — not a hand-picked
subset. Questions and answers persist as real conversation history; an earlier question
can be edited, which discards everything asked after it and generates a fresh answer.

### 5.2 How it works, end to end

1. Every turn (a user question, or an AI answer) is stored as its own row in a new
   table, `literature_chat_messages` — one row per turn, the same "append, don't
   overwrite" shape the multi-note system already used for notes.
2. Asking a new question (`ask_literature_stream()`):
   - builds a capsule for every saved paper (same `build_synthesis_capsule()` as
     Synthesis — reused, not reimplemented)
   - pulls the conversation history via
     `literature_chat_service.get_recent_history_for_prompt()`, which returns only the
     **most recent 8 messages** (`MAX_HISTORY_MESSAGES_FOR_PROMPT`), oldest first
   - streams `openai_service.stream_ask_literature(project_title, research_question,
     papers, history, question)`
   - on `done`, saves the new question **and** the new answer as two new rows via
     `add_chat_message()`
3. The page renders the full history (not just the capped 8) — the cap only limits what
   gets *resent to the model*, never what the user can see.

### 5.3 Why "whole library," not hand-picked — unlike Synthesis

This is the single most important conceptual contrast between Ask the Literature and
Paper Synthesis, and a good one to be ready to explain directly: **Synthesis is
deliberate and curated** — you're asking for one specific narrative across papers you
chose. **Ask the Literature is meant to feel like asking a colleague who has read
everything in the room** — a question could reasonably be about any paper in the
project, and forcing a paper selection before every question would mean re-selecting
before every single follow-up, which defeats the "conversational" feel entirely.

### 5.4 Prompt budgeting — the part most worth understanding deeply

`stream_ask_literature()` assembles **three variable-length pieces** into one prompt:
the papers block, the conversation history, and the new question. Unlike every other AI
call in the app (which lean on `_stream()`'s own default truncation — just cutting the
*end* off anything over `MAX_INPUT_CHARS`), this function caps **each piece separately,
before assembly**:

```
MAX_PAPERS_BLOCK_CHARS  = 8_000
MAX_HISTORY_BLOCK_CHARS = 4_000
MAX_QUESTION_CHARS      = 2_000
```

**Why this had to be different from the default truncation:** the default approach
keeps the *front* of the text and cuts the *end* — which is exactly backwards here. The
new question is assembled at the very **end** of the prompt (so it reads naturally after
"Conversation so far: ..."). If the whole assembled string were just truncated from the
end the normal way, a long conversation history could push the actual question itself
off the edge and get silently cut — the single worst thing that could happen, since the
question is the one thing the model absolutely must see in full. Capping each piece
*before* concatenation guarantees the question always survives completely intact,
regardless of how long the papers block or history gets.

### 5.5 Edit + Resend — a linear thread, not a branching one

`edit_and_truncate_message()` implements "edit an earlier question": it deletes every
message **after** the edited one (by `id`, not `created_at` — see note below) and then
rewrites that message's content, ready for a fresh answer to be generated.

**Why delete everything after it, instead of inserting the edit as a new branch (the way
some chat products let you explore alternate replies)?** Because this app models the
conversation as a **single linear thread**. Once a question changes, its old answer is
now stale (it answered a *different* question), and anything asked afterwards might have
implicitly depended on that now-replaced answer (e.g., "what about the second one?"
referring to something the stale answer introduced). The only internally consistent
choice, given a linear-thread model, is to drop the thread forward from the edit point —
a deliberate simplicity trade-off versus the considerably more complex alternative of
branching conversation trees.

**Why `id` instead of `created_at` for ordering/truncation?** A question and the answer
it triggers are written by two separate requests a moment apart — in practice their
timestamps are already in the right order, but `id` is the one column *guaranteed*,
by database auto-increment, to reflect insertion order with zero possibility of a tie.
It's a small defensive habit: prefer a guaranteed-unique ordering key over a
timestamp whenever both are available.

### 5.6 Technologies and reasoning

- Same streaming/NDJSON pattern as the other two features (reused, not reinvented).
- New table (`literature_chat_messages`) rather than reusing `Note` — a chat turn and a
  user note are conceptually different (an AI-authored, role-tagged, ordered
  conversation turn vs. a free-text user annotation), so a dedicated model was more
  correct than overloading an existing one.
- `get_recent_history_for_prompt(before_id=...)` — the same function also supports
  "give me history strictly before a given message," which `resend_ask_literature_message()`
  (triggered by Edit + Resend) uses so a resent question's own "history" is whatever
  came before the *original* version of that question — never including the version
  being replaced.

---

## 6. Cross-cutting design decisions worth being ready to defend

1. **No new migrations framework.** New columns (`Paper.matrix_*`,
   `ResearchProject.synthesis_*`) and the new `literature_chat_messages` table were
   added using the app's existing lightweight in-code column-migration helper
   (`_ADDED_COLUMNS` in `database_service.py`) rather than introducing Alembic or a
   similar framework. For a project at this scale, a dedicated migrations tool would add
   setup overhead disproportionate to the actual schema-change needs.

2. **AI-generated and manually-entered data are treated identically.** Both the
   Literature Matrix (AI extraction vs. manual edit) and — implicitly — the rest of the
   app never distinguish "AI said this" from "a human typed this" once a value is saved.
   This was a conscious choice: the Matrix's job is to hold the *correct* value for a
   cell, and correctness doesn't care about provenance. (Sprint 5 later adds *evidence*
   tracking on top of AI-generated text specifically — a separate concern from the
   Matrix's AI/manual symmetry.)

3. **Reused the capsule-building function across two features.** `build_synthesis_capsule()`
   is shared verbatim by Paper Synthesis and Ask the Literature — a clear sign the two
   features have the same underlying need (a compact, comparison-ready description of a
   paper) even though their *outputs* look completely different (one narrative, one
   conversation).

4. **Server-side re-validation everywhere user-supplied ids are used.** Both Paper
   Synthesis (`paper_ids` form field) and the rest of the app's paper/project access
   consistently re-check that an id actually belongs to the right owner/project before
   trusting it — a basic but easy-to-skip defensive habit worth calling out explicitly if
   asked about security considerations.

---

## 7. Quick-reference: likely defense questions

- **"Why three separate features instead of one generic 'ask AI anything about my
  papers' tool?"** Because they serve different intents: Matrix is for *structured*
  comparison you can export and reference like a table; Synthesis is for a *curated,
  polished narrative* across papers you deliberately chose; Ask the Literature is for
  *exploratory, open-ended* questions against the whole library. Collapsing them into
  one generic tool would lose the structure that makes each one useful for its specific
  job.
- **"What stops one user from reading another user's papers/projects?"** Every query for
  a specific project or paper filters by the *requesting user's own id*, not just the
  record's id (`get_project_for_user`, `user_can_access_paper`) — this predates Sprint 4
  but every new Sprint 4 route follows the same pattern.
- **"What happens if OpenAI is down or the key is missing?"** `openai_service.is_configured()`
  is checked before any AI call; routes show a clear "add a key" message instead of a
  confusing failed request, and the rest of each page (manual Matrix editing, reading
  existing synthesis/chat history) still works without a key.
- **"Why is the Matrix extraction exactly 4 paragraphs but the synthesis is 5–8?"** The
  Matrix's four fields are a *fixed schema* (Methodology/Sample/Findings/Limitations) —
  always exactly those four, so always exactly four paragraphs. The synthesis has no
  fixed schema; 5–8 is a *range* because how much there is to say genuinely depends on
  how many papers were selected and how much they overlap or diverge.
