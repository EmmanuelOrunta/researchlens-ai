# Automated Testing — Sprint 5 Defense Notes

*A plain-English guide for the team. No coding background needed — if you can
read a sentence, you can follow this.*

---

## 1. What this feature actually is, in one sentence

Instead of a person manually re-clicking through the whole app after every
code change to check nothing broke, we wrote that same checking — register
an account, try a wrong password, search for papers, ask the AI a question
— as code, so a computer can do all of it automatically, in under ten
seconds, any time we want.

Think of it like a pre-flight checklist for a pilot. Nobody re-invents the
checklist from memory before every flight — it's written down once, and run
through, item by item, every single time, so nothing gets forgotten.

---

## 2. The problem we were solving (the "why")

By Sprint 4, this app had grown to cover accounts, search, and four separate
AI features. Every time we changed one piece of code, there was a real risk
of accidentally breaking something else — a classic problem in software
called a *regression* (something that used to work, quietly stops working).
Catching that by hand would mean manually re-testing registration, login,
search, and all four AI features, by clicking through the whole app, every
single time anyone changed anything. That's slow, easy to skip under time
pressure, and easy to do inconsistently (a tired person checking at 2am
might just miss something a fresh person wouldn't).

We also specifically needed confidence in one risky area: our AI features
call out to a real, external, paid service (OpenAI). If that call fails for
any reason — no internet, no API key configured, a typo in a `.env` file —
what does the user actually see? A confusing crash? A frozen page? We needed
to know, automatically, every time, rather than finding out live in front of
judges.

So we asked: **how do we get fast, repeatable, always-up-to-date confidence
that the app still works — including how it behaves when something goes
wrong — without a person manually re-clicking through it every time?**

That question is what the automated test suite answers.

---

## 3. How we decided to build it (the design decisions)

**Decision 1 — Use Python's own built-in testing tool, no extra install
needed.** Python ships with a testing tool called `unittest` already built
in — nothing extra to install, nothing extra for a grader to set up on
their own machine. We write tests as small Python functions; `unittest`
finds them, runs them, and reports which passed and which didn't.

**Decision 2 — Never test against the real database.** The absolute last
thing we wanted was a test accidentally deleting or corrupting someone's
real saved projects. So every test run first points the whole app at a
brand-new, empty, temporary database file instead of the real
`database/researchlens.db` — created fresh, used only for that test run,
and thrown away afterward. The real database is never even opened during a
test run.

**Decision 3 — Drive the real app, not a simplified copy of it.** Rather
than writing separate, simplified pretend-versions of our login page or
search logic just to test them, the tests call the actual Flask routes
(`/register`, `/login`, `/logout`) and the actual functions our real pages
use. That matters because it means a passing test genuinely proves the real
app behaves correctly — not just that some separate test-only copy of the
logic does.

**Decision 4 — Split tests by what they can prove without the internet.**
Some things (does the de-duplication logic correctly recognize two results
as the same paper?) are pure logic we can test completely offline. Other
things (does Semantic Scholar actually return relevant results today?)
genuinely require a live internet connection and can't be meaningfully
faked. We were honest about that split: the offline-provable parts are
fully automated; the parts that truly need a live connection are called out
separately as a short manual checklist instead of being quietly skipped or
falsely claimed as "tested."

**Decision 5 — Specifically, deliberately test the worst case for AI
features: no API key at all.** This was the most important testing decision
of the sprint. Every one of our five AI features is tested not only with
good input, but also with `OPENAI_API_KEY` deliberately removed from the
environment, to confirm the app fails with one clear, plain-English message
— never a crash, never a frozen page — in exactly the failure scenario most
likely to actually happen live, in front of an audience, if something's
misconfigured.

---

## 4. The actual code, explained like you've never coded before

All the tests live in a `tests/` folder, as several files, each one starting
with `test_` (that's a code naming convention that tells the testing tool
"everything in here is a test"). You don't need to read or memorize the
code — just be able to explain, in your own words, what each piece checks
and why.

### a) The shared setup every test file relies on

```python
# tests/_dbtest.py
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(prefix="researchlens_test_", suffix=".db")
os.environ["RESEARCHLENS_DB_PATH"] = _TEST_DB_PATH

class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.client = flask_app.test_client()

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)
```

**In plain words:** this file runs first and creates one brand-new, empty,
temporary database file on disk, then tells the rest of the app (through an
environment variable, which is just a named setting the whole program can
read) to use that temporary file instead of the real one for the rest of
this test run. `setUp()` is a function that `unittest` automatically runs
*before every single test* — here, it wipes and rebuilds all the empty
tables, so each test always starts from a completely clean, empty database,
with no leftovers from whatever test ran just before it. `self.client` is a
pretend web browser — it can "click" links and "submit" forms against our
real Flask app without needing an actual browser window or an actual
running web server.

### b) A real example: testing that login actually works

```python
# tests/test_auth.py
def test_correct_credentials_log_in(self):
    response = self.client.post(
        "/login", data={"email": "loginuser@example.com", "password": "GoodPass1!"},
        follow_redirects=True,
    )
    self.assertIn(b"Dashboard", response.data)

def test_wrong_password_is_rejected(self):
    response = self.client.post(
        "/login", data={"email": "loginuser@example.com", "password": "WrongPass1!"},
    )
    self.assertIn(b"Incorrect email or password", response.data)
```

**In plain words:** `self.client.post("/login", data={...})` does exactly
what a real person does — fills in the email and password fields and hits
submit — except it's code doing it, instantly. `self.assertIn(...)` is the
actual "check": it says *"I expect to find this exact text somewhere in the
page that comes back — if it's not there, fail this test and tell me."* The
first test proves a correct login actually lands you on the Dashboard. The
second proves a wrong password shows the right error message instead of
silently failing or showing something confusing. There's also a third test
(not shown here) proving that an unknown email shows that *exact same*
generic error — on purpose, so a login attempt can't be used to figure out
which email addresses even have an account on our app.

### c) Testing the AI safety net — the single most important file

```python
# tests/test_ai_stream_guards.py
class MissingApiKeyGuardTests(unittest.TestCase):
    def setUp(self):
        self._real_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._real_key is not None:
            os.environ["OPENAI_API_KEY"] = self._real_key

    def test_summarize_paper_without_a_key(self):
        event = _only_event(stream_summarize_paper(
            "A Paper", "Jane Smith", 2024, "A real abstract with real content."
        ))
        self.assertIn("OPENAI_API_KEY", event["error"])
```

**In plain words:** `setUp()` here temporarily removes `OPENAI_API_KEY`
from the environment — even if a real key is sitting in a developer's own
`.env` file, this test makes sure, for just this one check, the app behaves
as if no key were configured at all. It then calls the real AI Summary
function directly, with otherwise-perfectly-valid input, and checks that
instead of hanging, crashing, or throwing a confusing technical error, it
comes back with one clear message that actually mentions `OPENAI_API_KEY` —
in other words, a message a non-technical user could read and understand
("AI isn't set up") rather than a raw error dump. `tearDown()` then puts the
real key back exactly as it was, every time, whether the test passed or
failed, so this never permanently changes anything about the developer's
own setup. This exact pattern is repeated for all five AI features
(Summary, Relevance Analysis, Matrix extraction, Synthesis, Ask the
Literature) — 5 tests, one per feature.

A second group in the same file checks the opposite situation — bad *input*
rather than a missing key (an empty paper, no research question typed, too
few papers for a synthesis) — and confirms each one is rejected politely,
before the app would ever even try to contact OpenAI.

### d) Testing the AI's honesty mechanism (Evidence Tracking)

```python
# tests/test_evidence_service.py
def test_quote_not_present_is_not_verified(self):
    source = "This study surveyed 400 students and faculty across six institutions."
    self.assertFalse(es.verify_quote("interviewed 900 participants", source))

def test_curly_vs_straight_quotes_still_match(self):
    source = 'The authors call this "a widening policy gap."'
    self.assertTrue(es.verify_quote("a widening policy gap", source))
```

**In plain words:** this reuses Sprint 4's Evidence Tracking system (see
`Sprint4_Note_1_Evidence_Tracking.md`) and checks its core promise actually
holds: a made-up quote gets correctly flagged as unverified, while a real
quote that only *looks* different because of a typing-style quirk (curly
quotation marks vs. straight ones) doesn't get wrongly flagged just because
of that. There are over 20 tests like this in the file, each checking one
small, specific rule — a malformed line from the AI doesn't break the whole
evidence block, an overlong quote gets safely shortened instead of rejected,
a citation pointing at a paper that's since been deleted shows "no link"
instead of crashing the page, and so on.

### e) Testing what happens with messy, real-world data

```python
# tests/test_search_dedup.py
def test_same_doi_from_both_sources_produces_the_same_key(self):
    ss_paper = {"doi": "10.1000/ABC123", "title": "A Study of Things"}
    oa_paper = {"doi": "10.1000/abc123", "title": "A completely different title"}
    self.assertEqual(_dedupe_key(ss_paper), _dedupe_key(oa_paper))
```

**In plain words:** our app searches two different academic sources
(Semantic Scholar and OpenAlex) and needs to recognize when they both
returned the *same* paper, so we don't show a duplicate. This test proves
that logic works correctly even when the two sources format the paper's DOI
(its unique ID number) with different capitalization, and even give it a
slightly different title string — it's still recognized as one paper, not
two.

---

## 5. How it's implemented — the full journey, step by step

1. Someone runs one command: `python -m unittest discover -s tests -t . -v`
2. `tests/_dbtest.py` runs first (automatically, because every test file
   imports from it) and points the whole app at a brand-new, temporary,
   disposable database — the real database is never touched.
3. The testing tool finds every file in `tests/` starting with `test_`, and
   inside each one, every function starting with `test_`.
4. For each test: `setUp()` runs first (wiping and rebuilding empty tables,
   and — for the AI-key tests — temporarily removing the API key), then the
   test itself runs (the actual action and check), then `tearDown()` runs
   (restoring anything that was temporarily changed).
5. Each test prints `ok` the moment it passes, or a detailed explanation of
   exactly what went wrong if it fails — which line, what was expected,
   what actually happened.
6. Once every test has run, one summary line prints at the very end:
   `Ran 38 tests in 7.892s` / `OK` — that's the whole suite confirming
   nothing is broken, in under eight seconds.
7. This can be re-run after literally any code change, as many times as we
   want, for free — there's no reason not to run it constantly while
   developing.

---

## 6. Why this works well for our project

- It catches regressions (something that used to work quietly breaking)
  immediately, rather than during a live demo or, worse, after submission.
- It's honest about its own limits. We didn't claim to have "tested
  everything" — we automated everything that genuinely can be proven
  without a live network call or a human judgement call, and clearly
  labeled the rest (live search results, whether a generated AI answer is
  *factually* good) as a separate manual pass, see
  `docs/Sprint5_AI_Accuracy_Checklist.md`.
- The AI-safety-net tests in particular are a real, demonstrable,
  verifiable claim we can make in a defense: *"every AI feature in this app
  is tested to fail safely and explain itself, in its worst-case failure
  mode, not just its best case."* That's a specific, checkable engineering
  claim, not a vague one.
- It's fast and free to run, which means it actually gets run — a test
  suite that takes 20 minutes to run tends to get skipped under time
  pressure; one that takes 8 seconds doesn't.
- It never risks real data, because it never touches the real database at
  all — every run is fully disposable from start to finish.

---

## 7. Questions people might ask us, and simple answers

**Q: What's the difference between this and manual/usability testing?**
A: Automated tests check mechanical, provable things — does this exact
input produce this exact, correct result, every time, with zero human
effort. Usability testing is a human actually using the app and judging
things a computer can't, like "is this confusing?" We did both — see
`docs/Sprint5_Usability_Testing_Script.md` for the human side.

**Q: Does this prove the AI's answers are actually correct?**
A: No, and we're upfront about that. These tests prove the app *behaves
correctly around* the AI — handles bad input gracefully, fails clearly when
unconfigured, correctly checks whether a cited quote is real. Whether a
live, successful AI answer is actually factually good is a human judgement
call, covered separately in `docs/Sprint5_AI_Accuracy_Checklist.md`.

**Q: Could this accidentally spend real OpenAI credits while testing?**
A: No — every test is designed to never actually call OpenAI. The
input-validation tests fail before that point entirely, and the missing-key
tests deliberately remove the API key first, specifically to guarantee no
real, billed network request ever happens during an automated test run.

**Q: What happens if a test fails?**
A: It prints exactly which test failed and why (what was expected versus
what actually happened), while every other test still runs normally. One
failure doesn't hide or block the rest of the results.

**Q: Why does it use a temporary database instead of the real one?**
A: So running tests can never accidentally delete, overwrite, or corrupt
anyone's real saved projects. Every test run starts from a completely
empty, disposable database and throws it away afterward.

**Q: How many tests are there, and what do they cover?**
A: As of this sprint, well over 38 (the exact count grows as we add more).
They cover: registration and login (including rejecting weak passwords and
duplicate emails), session protection (private pages require login), search
de-duplication and year filtering, the Evidence Tracking "is this quote
real" mechanism, Literature Matrix saving, Paper Synthesis's fallback logic
and 2-paper minimum, and — the biggest group — every one of the five AI
features' behavior on both bad input and a missing API key.

**Q: Do these tests run automatically, or does someone have to remember to
run them?**
A: Right now, someone runs the one command manually. They're written so
that in a larger project this exact same suite could be wired up to run
automatically every time code is pushed — we just didn't need that
infrastructure for a project this size.
