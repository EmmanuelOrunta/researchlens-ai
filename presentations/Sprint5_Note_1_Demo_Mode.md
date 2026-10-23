# Demo Mode — Sprint 5 Defense Notes

*A plain-English guide for the team. No coding background needed — if you can
read a sentence, you can follow this.*

---

## 1. What this feature actually is, in one sentence

One command fills a real account in our real database with a complete,
already-finished example project — so when we present, we're clicking
through real screens with real-looking results already sitting there,
instead of hoping a live internet connection and a live AI call both
cooperate at exactly the right moment.

Think of it like a model home. Everything in it is real and walkable, but
nobody's actually living there day to day — it's set up in advance,
specifically so it looks its best when someone comes to view it.

---

## 2. The problem we were solving (the "why")

Our app's core features — searching for papers, summarizing them with AI,
comparing several papers, chatting with an AI about your saved library — all
depend on things outside our control working at the exact moment we demo
them: the presentation room's WiFi, Semantic Scholar/OpenAlex being
reachable, and OpenAI's API actually responding. Any one of those failing mid-demo, in front of whoever's grading us, turns a five-minute walkthrough into an awkward "it normally works, I promise."

We also didn't want our demo to look thin. A brand-new account has an empty
dashboard, zero saved papers, and nothing to click into — not a great first
impression, and it means improvising a live search and a live AI call just
to have something to show.

So we asked: **how do we guarantee a good-looking, fully clickable demo that
doesn't depend on anything outside our own laptop working correctly?**

That question is what Demo Mode answers.

---

## 3. How we decided to build it (the design decisions)

**Decision 1 — Write the results by hand instead of generating them live.**
Rather than having the script actually call OpenAI to generate a summary, a
synthesis, and a chat answer (which would just reintroduce the exact
network/API dependency we're trying to avoid), we wrote realistic-sounding
AI output ourselves, directly as plain text in the script. The demo account
ends up looking indistinguishable from one that used the AI live, because
it reuses the AI features' real database fields and real page templates —
it's only the *generation* step that's skipped.

**Decision 2 — Go through the app's own functions, not a shortcut.** The
script doesn't poke values directly into the database by hand. It calls the
exact same functions the real app calls when a real user saves a paper, sets
a matrix field, or sends a chat message (`save_paper_to_project()`,
`set_paper_matrix_fields()`, `add_chat_message()`, and so on). That matters
for honesty and reliability: the demo data is guaranteed to be shaped
exactly like real data the app produces, so there's no chance of the demo
page looking different from how it'd look for a real user, or breaking
because the script wrote something the real app's pages don't expect.

**Decision 3 — Make it safe to re-run, every single time.** A rehearsal
script that leaves junk behind if you run it twice would actually make
things riskier, not safer, right before presenting. So the script's first
move is always to find any previous demo account by its email address,
delete it completely (every saved paper, every chat message, everything
cascades away with it), and only then build a fresh one. Running it the
morning of presentation day always leaves exactly one clean, correct demo
project — never a pile of leftover duplicates from an earlier rehearsal.

**Decision 4 — Leave two papers deliberately unfinished.** Three of the five
demo papers have their Literature Matrix fields already filled in; two
(Okafor and Dubois) are left blank on purpose, exactly like a freshly-saved
paper looks before anyone's analyzed it. That's intentional: if the
presentation room's WiFi *does* happen to work, there's still something real
to click "Extract with AI" on, live, as a bonus — without the core
walkthrough ever depending on that working.

---

## 4. The actual code, explained like you've never coded before

All of this lives in one file: `scripts/seed_demo_data.py`. You run it from
a terminal with `python scripts/seed_demo_data.py` — you don't need to open
or edit the file itself, just understand what it's doing when it runs.

### a) Wiping any old demo account first

```python
def _wipe_existing_demo_account(session):
    existing = get_user_by_email(session, DEMO_EMAIL)
    if existing is None:
        return
    for project in get_projects_for_user(session, existing.id):
        delete_project(session, project)
    delete_user(session, existing)
```

**In plain words:** before building anything new, this checks "is there
already a demo account from last time?" If there is, it deletes that
account's project (which automatically takes its saved papers and chat
history with it) and then deletes the account itself. If there isn't one
yet, it just moves on. This is the "clean slate" step — it's what makes
re-running the script any number of times always safe.

### b) Creating the account and the project

```python
user = create_user(session, name=DEMO_NAME, email=DEMO_EMAIL,
                    password_hash=hash_password(DEMO_PASSWORD))

project = create_project(
    session, user_id=user.id,
    title="Generative AI in Higher Education",
    research_question="How is generative AI being adopted and governed in university teaching and learning?",
    research_field="Education Technology",
    keywords="ChatGPT, generative AI, higher education, academic policy",
)
```

**In plain words:** this is the exact same `create_user()` and
`create_project()` code a real registration and a real "New Project" button
use — the script is just calling them directly from a Python file instead of
through the website's forms. `hash_password()` makes sure even the demo
account's password is stored securely, scrambled the same way a real user's
would be, not as plain readable text.

### c) Adding papers, and deliberately leaving two incomplete

```python
for paper in (chan, schwarz, okafor, park, dubois):
    save_paper_to_project(session, project.id, paper.id)

set_paper_matrix_fields(session, chan, methodology="...", sample="...",
                         findings="...", limitations="...")
set_paper_matrix_fields(session, schwarz, ...)
set_paper_matrix_fields(session, park, ...)
# okafor and dubois: deliberately left un-extracted
```

**In plain words:** all five papers get saved to the project the normal
way. Then only three of them (`chan`, `schwarz`, `park`) get their Matrix
fields (methodology, sample, findings, limitations) filled in by calling
`set_paper_matrix_fields()` — the same function the real "Extract with AI"
button calls. The other two are simply never passed to that function, so
they stay blank, exactly as a brand-new saved paper would look.

### d) Writing out an AI Summary and its evidence, by hand

```python
chan_summary = (
    "Chan and Hu (2023) investigate how generative AI tools such as "
    "ChatGPT are reshaping teaching and learning in universities..."
    # ...six paragraphs total
)
set_paper_summary(session, chan, chan_summary, evidence={
    "3": {"quote": "surveying 400 students and faculty across six institutions", "verified": True},
    "4": {"quote": "faculty policy has not kept pace with how widely students already rely on these tools", "verified": False},
})
```

**In plain words:** instead of asking the real AI to write this, the six
paragraphs of summary text are typed directly into the script as a string,
written to read naturally, the same way a real AI Summary reads. The
`evidence={...}` part plugs directly into the same Evidence Tracking system
from Sprint 4 (see `Sprint4_Note_1_Evidence_Tracking.md`) — it marks which
paragraphs have a "verified" supporting quote versus an "unverified" one, so
the demo page shows the exact same green-checkmark / amber-question-mark
evidence chips a real, live-generated summary would show.

### e) The two things printed at the end

```python
print("Demo account ready.")
print(f"  Email:    {DEMO_EMAIL}")
print(f"  Password: {DEMO_PASSWORD}")
```

**In plain words:** when the script finishes, it just prints the login
details straight to the terminal, so whoever's running it right before
presenting doesn't have to remember them or go dig through the code.

---

## 5. How it's implemented — the full journey, step by step

1. Someone runs `python scripts/seed_demo_data.py` from a terminal, ideally
   on the laptop that will actually present, shortly before presenting.
2. The script connects to the app's real database (`database/researchlens.db`
   — the same file `python app.py` itself uses).
3. It looks for a demo account from any previous run and, if found, deletes
   it completely — project, saved papers, chat history, the account itself.
4. It creates a fresh demo account and one project, "Generative AI in
   Higher Education," using the app's own account- and project-creation
   functions.
5. It creates five papers and saves all five to that project.
6. It fills in the Literature Matrix for three of them, using the app's own
   matrix-saving function — leaving two deliberately blank.
7. It writes a six-paragraph AI Summary (with evidence) onto one paper, two
   relevance analyses, one three-paper Paper Synthesis (with evidence), and
   a two-turn Ask the Literature conversation — all using the exact same
   database functions the live features use, just fed hand-written text
   instead of a real AI response.
8. It prints the login details and a short confirmation to the terminal.
9. From that point on, logging in as `demo@researchlens.ai` and clicking
   through dashboard → project → paper detail → matrix → synthesis → chat
   needs **zero** network calls — everything on that path is already saved.

---

## 6. Why this works well for our project

- It removes the single biggest risk in any live software demo: depending
  on something you don't control (WiFi, a third-party API) working at
  exactly the right second, in front of the people grading you.
- It's honest, not faked — the demo account isn't a mockup or a set of
  screenshots pretending to be the app. It's the real app, the real
  database, the real page templates, the real login flow. Only the AI
  *generation* step was skipped; everything downstream of it is genuine.
- It's fast to reset. One command, a few seconds, and you have a clean,
  known-good demo project again — useful not just the morning of
  presenting, but after every rehearsal too.
- It reuses the same five-paper "Generative AI in Higher Education"
  project used elsewhere in this project (the README screenshots, the
  slide decks), so everything we show tells one consistent story instead of
  a different example every time.

---

## 7. Questions people might ask us, and simple answers

**Q: Isn't this just faking the demo?**
A: No — it's real data in the real database, reached through the real app.
The only thing skipped is actually calling OpenAI live to *generate* the
AI text; the text itself was written by us and saved exactly the way a
real AI response would be saved, so every feature works normally on top of
it.

**Q: What if someone wants to see the AI actually working live, not just
pre-filled results?**
A: That's exactly why two of the five papers are left with blank Matrix
fields — if the room's WiFi cooperates, there's a real "Extract with AI"
button sitting there ready to click, live, as a bonus.

**Q: Does this touch our real, personal data?**
A: No. It only ever creates, wipes, and recreates one specific account
(`demo@researchlens.ai`). It never touches any other account's projects or
papers.

**Q: What happens if you run the script twice in a row by accident?**
A: Nothing bad — it's specifically designed to be safe to re-run. It always
deletes the previous demo account first, so you just end up with the same
clean result, never duplicates.

**Q: Why not just take screenshots instead of building this?**
A: Screenshots can't be clicked through. Demo Mode gives us a real,
interactive walkthrough — clicking into a paper, opening the matrix,
scrolling the chat — which is far more convincing and far more useful if
someone asks to see a specific feature we didn't plan to show.

**Q: Is the demo password a real security risk?**
A: No — it's a low-stakes, made-up password for a disposable demo account
that gets wiped and recreated before every use, not a real credential
protecting anything sensitive.
