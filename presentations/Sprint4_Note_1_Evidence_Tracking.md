# Evidence Tracking — Sprint 4 Defense Notes

*A plain-English guide for the team. No coding background needed — if you can
read a sentence, you can follow this.*

---

## 1. What this feature actually is, in one sentence

Every time our AI writes an answer, it also has to show its "receipt" — the
exact sentence, from the exact paper, that it got that answer from — and the
app double-checks that receipt is real before showing it to you.

Think of it like a student handing in an essay with every claim footnoted,
except the footnotes are checked by someone else before the essay is accepted.

---

## 2. The problem we were solving (the "why")

Our app uses AI (OpenAI) to summarize papers, combine several papers into one
write-up, and answer questions about a user's saved library. The risk with
any AI like this is simple: **it can sound confident while being wrong.** It
might say "Smith (2023) found that remote work improves productivity" when
Smith (2023) never said that at all. This is called *hallucination* — the AI
isn't lying on purpose, it's just predicting plausible-sounding text, and
sometimes "plausible" and "true" don't match.

For a research tool, that's a serious problem. A student doing a literature
review can't responsibly quote something the AI invented. So we asked: **how
do we let the AI write naturally, but still let the user verify every claim
without having to re-read the whole paper themselves?**

That question is what Evidence Tracking answers.

---

## 3. How we decided to build it (the design decisions)

**Decision 1 — Ask the AI to show its work, in a small hidden block.**
Instead of trying to guess afterwards which sentence the AI "meant," we
simply told the AI, as part of its instructions: *"After you finish your
answer, add a short list — one line per paper/paragraph you drew from, with
a short word-for-word quote proving it."* This is far easier than the
alternative (trying to automatically match AI prose back to the source text
after the fact), because the AI already knows what it based its answer on —
we just have to ask it to tell us.

**Decision 2 — Never trust the AI's quote blindly. Check it ourselves.**
Asking the AI isn't enough — it could still misquote. So our own code takes
that quote and literally searches for it inside the paper's real text. If
the quote is found, we mark it ✅ **Verified**. If it isn't found exactly,
we still show it (don't hide it — hiding looks like we're covering something
up) but we label it "not verified," so the reader knows to double-check it
themselves.

**Decision 3 — Keep the "receipt" block invisible to the reader, but strip
it out cleanly.** The AI writes its answer live, word by word (like watching
someone type). The evidence list has to come after the answer but should
never actually flash on screen as part of the essay. So the block starts
with a special marker that would never normally appear in regular writing,
and our code (and the on-screen typing effect) always cuts everything from
that marker onward before displaying text.

**Decision 4 — Build this once, reuse it everywhere.** Evidence Tracking
isn't just one feature bolted onto one page — it is reused by all three
AI-answer features in this sprint: the single-paper AI Summary, Paper
Synthesis (several papers), and Ask the Literature (chat). Rather than
writing this logic three times, we built one shared file,
`evidence_service.py`, and every AI-answering function calls into it. This
means a fix or improvement in one place automatically improves all three
features — less code to maintain, and one place to trust.

---

## 4. The actual code, explained like you've never coded before

All of this lives in one file: `services/evidence_service.py`. Below are the
three pieces that matter most. You do not need to memorize the code — just
be able to explain, in your own words, what each piece does.

### a) The instruction we give the AI

```python
MULTI_EVIDENCE_INSTRUCTION = (
    "After your answer, on new lines, add a machine-readable evidence "
    "block... one line per paper you actually drew from... "
    "N: \"a short excerpt, quoted VERBATIM from that paper's own material\""
)
```

**In plain words:** this is just a sentence of instructions we glue onto the end of every prompt we send to the AI. It's the same idea as telling a student "show your working" on a math test. We're not writing any clever logic here — we're literally asking the AI nicely, in English, to list which
papers it used and quote them exactly.

### b) Checking if the quote is actually real

```python
def verify_quote(quote: str, source_text: str) -> bool:
    quote = _normalize_for_match(quote)
    source_text = _normalize_for_match(source_text)
    return bool(quote) and bool(source_text) and quote in source_text
```

**In plain words:** this is a small recipe (programmers call it a
"function") that takes two things — the quote the AI claims it used, and the
paper's real text — and simply asks: *"is this exact quote sitting somewhere
inside the real text?"* `quote in source_text` is Python's way of saying
"search for this phrase inside this bigger block of text" — exactly like
using Ctrl+F to search a document. If it's found, the answer is `True`
(verified). If not, `False` (not verified). The "normalize" step before that
just lowercases everything and smooths out punctuation differences (like
curly quotes `"` vs straight quotes `"`) so a verified quote doesn't get
wrongly rejected over a typing style difference that doesn't actually change
the meaning.

### c) Splitting the AI's answer from its hidden evidence list

```python
def extract_evidence_block(raw_text: str):
    marker_index = raw_text.find(EVIDENCE_BLOCK_MARKER)
    if marker_index == -1:
        return raw_text.strip(), []
    clean_text = raw_text[:marker_index].rstrip()
    ...
```

**In plain words:** when the AI's full response comes back, it's really two
things stuck together: the readable answer, and — after our special hidden
marker — the evidence list. This code finds where that marker starts, and
cuts the text there: everything *before* the marker is the actual answer the
user reads (`clean_text`); everything *after* it gets picked apart, line by
line, into the list of quotes. If the AI ever forgets to include the marker
at all (AI isn't perfect), this code doesn't crash — it just treats the
whole thing as a normal answer with no evidence attached, so nothing ever
breaks the page.

### d) Putting it together into something the screen can show

```python
def build_paragraph_evidence(raw_text: str, source_text: str):
    clean_text, raw_entries = extract_evidence_block(raw_text)
    evidence_by_paragraph = {}
    for key, quote in raw_entries:
        evidence_by_paragraph[key] = {
            "quote": quote,
            "verified": verify_quote(quote, source_text or ""),
        }
    return clean_text, evidence_by_paragraph
```

**In plain words:** this is the "assembly line" step. It takes the raw
answer, runs the split-it-apart step (c), then runs the real-or-not check
(b) on every single quote, and packages the result into a neat list the web
page can loop over and display as little expandable "Source passage" chips
— the green checkmark or amber question-mark you see on the Evidence
Tracking slide.

---

## 5. How it's implemented — the full journey, step by step

1. A user asks for an AI Summary (or a Synthesis, or asks a question in the
   chat).
2. Our code sends the AI a prompt that **always ends** with the "show your
   work" instruction from section 4a.
3. The AI streams its answer back, word by word, finishing with its hidden
   evidence block.
4. The moment the AI says "I'm done," our code (section 4c) slices off the
   hidden block.
5. Each quote in that block gets checked against the real paper text
   (section 4b) — verified or not.
6. The clean answer and its evidence list are saved to the database
   together, so they're still there the next time the page loads — not just
   while the AI is mid-answer.
7. The page displays the answer normally, with small clickable "Source
   passage" labels under it. Clicking one reveals the quote and whether it
   was verified.

---

## 6. Why this works well for our project

- It directly supports our project's whole purpose: helping someone do a
  **trustworthy** literature review, not just a fast one. A summary nobody
  can verify isn't actually useful for academic work.
- It's honest by design — we never hide an unverified quote, we just label
  it. That's a deliberate ethical choice: looking "too polished" by hiding
  uncertainty would be worse than showing it plainly.
- It's reusable. One small file supports three different features, which
  kept Sprint 4 manageable instead of writing (and testing) this three
  separate times.
- It fails safely. If the AI forgets the format, skips a quote, or the quote
  doesn't match — nothing crashes, the user just sees fewer or unverified
  chips instead of a broken page.

---

## 7. Questions people might ask us, and simple answers

**Q: What if the AI makes up a quote entirely?**
A: We check every quote against the actual paper text. If it's not really
there, we still show it but mark it "not verified," so nobody mistakes an
invented quote for a confirmed one.

**Q: Why show unverified quotes at all instead of just deleting them?**
A: Because "not verified" doesn't always mean "fake" — sometimes the AI
paraphrased slightly instead of word-for-word quoting. Hiding it would look
like the app is covering something up. Showing it, clearly labeled, is more
honest and still useful.

**Q: Does this slow down the AI's answer?**
A: No — the AI is already generating the evidence block as part of the same
single answer, so there's no extra waiting. The only extra step is our quick
text-search check, which is near-instant.

**Q: What happens if a paper has no text to check against (e.g. no abstract
was saved)?**
A: The search simply can't find a match, so the quote is marked unverified
rather than the app crashing or guessing.

**Q: Is this the same mechanism for all three AI features (Summary,
Synthesis, Ask the Literature)?**
A: Yes — one shared file (`evidence_service.py`) powers all three. Summary
checks one paper's own text; Synthesis and Ask the Literature check against
whichever of several papers the quote claims to be from.

**Q: Could someone trick the system with a fake paper?**
A: No — the AI is only ever given the real, saved text of papers the user
already added to their own project. It can't invent a new "paper" to quote
from; every quote is checked only against real, saved paper text.

**Q: Why 30 words max per quote?**
A: Keeps quotes short and genuinely "pointing at evidence" rather than
copy-pasting huge chunks of the source paper, which would be closer to
plagiarism than citation.
