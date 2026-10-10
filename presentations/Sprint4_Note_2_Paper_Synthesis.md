# Paper Synthesis — Sprint 4 Defense Notes

*A plain-English guide for the team. No coding background needed.*

---

## 1. What this feature actually is, in one sentence

You pick two or more papers you've saved, and the AI writes one connected
piece of writing that compares and combines them — not six separate
summaries stapled together, but a single flowing discussion, the way a real
literature review's "Synthesis" section reads.

---

## 2. The problem we were solving (the "why")

Our app already had a way to summarize **one paper at a time**. But real
literature reviews don't work paper-by-paper — the valuable part is
comparing papers against each other: where do they agree, where do they
disagree, what's missing across all of them together. Doing that by hand
means reading five papers, then manually writing paragraphs that reference
all of them without flipping back and forth. That's slow and easy to get
wrong.

So the question was: **can the AI do that cross-paper comparison for the
user, while still being honest about exactly which papers it's drawing
from?**

---

## 3. How we decided to build it (the design decisions)

**Decision 1 — Require at least two papers, and say so clearly.**
A "synthesis" of one paper isn't a synthesis at all — it's just a summary
wearing a different name. So before anything else happens, we check: did the
user pick two or more papers? If not, we stop immediately and tell them why,
instead of quietly generating something that isn't what they asked for.

**Decision 2 — Don't just paste the full text of every paper into the AI
prompt.** Papers can be long. Sending five full papers to the AI every time
would be slow, expensive, and risk going over what the AI can actually read
in one go. Instead, we reduced each paper down to a short "capsule" — its
Matrix fields if the user filled those in (Methodology, Sample, Findings,
Limitations), or its abstract if not. This keeps every request fast and
affordable while still giving the AI the substance it needs.

**Decision 3 — Tell the AI exactly what shape to write in, not just "write
something."** We give the AI a structured recipe: open by naming the shared
theme across the papers, then compare them directly by name, then point out
what they all lean on in common, then critique the body of work as a whole,
then close with what it all means. This is what keeps the output reading
like an actual synthesis section instead of a random ramble.

**Decision 4 — Never trust which papers the user "selected" without
checking.** The list of ticked checkboxes comes from the user's browser,
which technically anyone could tamper with (for example, submitting a paper
ID that belongs to someone else's project). So before generating anything,
our server re-checks every submitted paper ID against that specific
project's own saved papers, and throws away anything that doesn't belong.

**Decision 5 — Save the result with the exact list of papers it came from.**
A synthesis is only useful if you can tell, later, which papers it's
actually based on. So when we save the finished synthesis, we save the
paper IDs right alongside it — not just the text.

---

## 4. The actual code, explained like you've never coded before

### a) Reducing a paper down to something the AI can quickly read

(`services/paper_service.py` → `build_synthesis_capsule`)

```python
def build_synthesis_capsule(paper) -> str:
    matrix_parts = []
    if paper.matrix_methodology:
        matrix_parts.append(f"Methodology: {paper.matrix_methodology}")
    ...
    if matrix_parts:
        return "\n".join(matrix_parts)
    if paper.abstract:
        return f"Abstract: {paper.abstract}"
    return "No abstract, extracted text, or matrix fields available for this paper."
```

**In plain words:** think of this as writing an index card for one paper.
It checks, in order: "Do we have Methodology/Sample/Findings/Limitations
filled in for this paper? Use those." If not: "Do we at least have an
abstract? Use that instead." If there's truly nothing at all, it says so
plainly rather than pretending there's content. This index card — not the
whole paper — is what actually gets sent to the AI.

### b) Refusing to synthesize fewer than two papers

(`services/openai_service.py` → `stream_synthesize_papers`)

```python
if len(papers) < 2:
    yield {"error": "Select at least 2 papers to synthesize."}
    return
```

**In plain words:** `len(papers)` just means "how many papers are in this
list." This line reads almost like English: "if the number of papers is
less than 2, stop here and hand back this error message instead of doing
anything else." It's the very first thing that runs, before any time or
money is spent talking to the AI.

### c) Turning each paper's index card into one numbered block for the AI

```python
papers_block = "\n\n".join(
    f"Paper {i + 1}:\nTitle: {paper['title']}\nAuthors: {paper['authors']}\n"
    f"Year: {paper['year']}\n{paper['capsule']}"
    for i, paper in enumerate(papers)
)
```

**In plain words:** this goes through the list of selected papers one at a
time and writes each one out as "Paper 1: ...", "Paper 2: ...", and so on,
then glues them all together with blank lines in between. This numbered
list is what lets us later say "cite Paper 2" and know exactly which real
paper that refers to — it's the same numbering trick Evidence Tracking
relies on (see that note).

### d) Double-checking which papers the user is actually allowed to use

(`routes/papers_routes.py` → `synthesis_stream`)

```python
seen = set()
ordered_ids = []
for pid in requested_ids:
    if pid in papers_by_id and pid not in seen:
        seen.add(pid)
        ordered_ids.append(pid)
```

**In plain words:** `papers_by_id` is the list of papers that genuinely
belong to this project, looked up fresh from our own database — not taken
on trust from whatever the browser sent. This code walks through every
paper ID the browser submitted and only keeps it if it's (1) actually one of
this project's real papers, and (2) not already added (so ticking the same
box twice, or a glitch sending a duplicate, doesn't count a paper twice).
Anything that fails either check is silently dropped — the user never even
notices, because it was never a legitimate request anyway.

### e) Saving the finished synthesis together with its source papers

(`services/project_service.py` → `set_project_synthesis`)

```python
def set_project_synthesis(session, project, text, paper_ids, evidence=None):
    project.synthesis_text = text
    project.synthesis_paper_ids = ",".join(str(paper_id) for paper_id in paper_ids)
    project.synthesis_generated_at = datetime.utcnow()
    session.commit()
```

**In plain words:** once the AI finishes writing, this saves three things
together: the actual text, the list of which paper IDs it was built from
(written as a simple comma-separated list, like "3,7,12"), and the time it
was generated. `session.commit()` is just the "save" button — it writes
these changes permanently to the database so they're still there the next
time anyone opens the page.

---

## 5. How it's implemented — the full journey, step by step

1. User opens the Paper Synthesis page and ticks the checkboxes next to two
   or more saved papers.
2. User clicks "Generate Synthesis." The browser sends the list of ticked
   paper IDs to our server.
3. The server re-checks those IDs against this project's real saved papers
   (section 4d) — anything that doesn't belong gets dropped.
4. If fewer than 2 valid papers remain, the server stops and shows an error
   (section 4b).
5. Otherwise, each remaining paper is turned into a short index card
   (section 4a), numbered and combined into one prompt (section 4c).
6. The AI writes its synthesis live, streaming word by word to the screen —
   plus its hidden evidence block (see the Evidence Tracking note).
7. Once finished, the clean text, its evidence, and the exact paper IDs used
   are all saved together (section 4e), so reopening the page later still
   shows this same synthesis and which papers it came from.

---

## 6. Why this works well for our project

- It solves a real literature-review task — comparing papers, not just
  listing them — which is the part of a review that actually takes a human
  the longest.
- Using short "index cards" instead of full paper text keeps it fast and
  keeps the AI focused on what matters, rather than drowning in raw text.
- The security re-check (section 4d) means a user can never accidentally
  (or deliberately) generate a synthesis using a paper that isn't really
  theirs.
- Saving the exact source paper list next to the result means a synthesis
  is never a "mystery" — anyone, including an instructor reviewing our
  project, can see exactly what it was built from.

---

## 7. Questions people might ask us, and simple answers

**Q: What stops someone from generating a "synthesis" of just one paper?**
A: The very first check in the code refuses to run at all unless at least
two papers were validly selected — it returns a plain error instead.

**Q: Why not just send the AI the full text of every paper?**
A: Full papers can be very long; sending all of them every time would be
slow, costly, and risks going past what the AI can read in one request. The
short "index card" (Matrix fields or abstract) keeps requests efficient
while still giving the AI real substance to work from.

**Q: What if I pick 5 papers but one of them doesn't actually belong to
this project?**
A: The server independently looks up this project's real saved papers and
silently drops anything that doesn't match — it never trusts the list sent
from the browser as-is.

**Q: Can I regenerate the synthesis with a different set of papers later?**
A: Yes — generating a new one simply overwrites the saved text and its
paper list; we keep the current synthesis, not a history of every past one
(that's a deliberate simplicity choice for this sprint).

**Q: How do we know the synthesis didn't just make something up about a
paper?**
A: Every claim that cites a specific paper gets a checkable quote through
Evidence Tracking — see that note for exactly how quotes are verified
against the real paper text.

**Q: Why not let the AI just freely pick which papers to discuss?**
A: Because the whole point is comparing a *specific* set the user chose
deliberately for this analysis — letting the AI wander off to other saved
papers would make the result unpredictable and harder to trust.
