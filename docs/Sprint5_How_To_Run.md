# Sprint 5 — How to Actually Run This (step by step, zero assumed knowledge)

*You've already done this once before, to run the app itself (see the README's "quick
walkthrough"). This is the exact same kind of thing, just two new commands. Follow
along in order — don't skip ahead.*

## Step 0 — Open a terminal in the right folder

1. Open **File Explorer** and go to your `researchlens-ai-flask` folder (the one in
   Downloads).
2. Click once in the empty address bar at the top of the window (where the folder path
   is shown), type `powershell`, and press **Enter**. A black/blue terminal window
   opens, already sitting "inside" this folder.

Everything below gets typed into that window, one line at a time, pressing **Enter**
after each line.

## Step 1 — Turn on the project's Python environment

```
venv\Scripts\Activate.ps1
```

You'll know it worked because the line in the terminal now starts with `(venv)`. If
Windows shows a red error about "running scripts is disabled," type this instead, then
try Step 1 again:

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Step 2 — Create the demo account (Sprint 5, item 1)

```
python scripts/seed_demo_data.py
```

You should see a few lines end with something like:

```
Demo account ready.
  Email:    demo@researchlens.ai
  Password: DemoDay2026!
  Project:  'Generative AI in Higher Education' (1 project, 5 saved papers)
```

That's it — that account now exists in your real database, with everything
pre-filled. You can run this exact command again any time (e.g. the morning of your
presentation) and it'll always reset back to this same clean state.

**To see it:** run `python app.py` like you normally do, open the printed address in
your browser, and log in with the email/password above.

## Step 3 — Get your test results (Sprint 5, items 4 & 6)

Back in the same terminal (stop the app first with `Ctrl+C` if it's still running):

```
python -m unittest discover -s tests -t . -v
```

## Step 4 — Reading what comes back

You'll see a long list of lines, one per check, each ending in `ok` or `FAIL`/`ERROR`,
then a summary at the very bottom. Two possible endings:

**Good outcome** — ends with:
```
OK
```
Every check passed. You're done with this step — go tell your team "all 30-ish
automated checks pass," and move on to the two human-run worksheets (usability +
AI-accuracy — see `docs/Sprint5_Plan.md` items 2–3).

**Something failed** — ends with something like:
```
FAILED (failures=1, errors=0)
```
Scroll up from the bottom — each failure prints which check it was and why, in plain
English (e.g. `AssertionError: b'Incorrect email' not found in response.data`). Copy
that whole red block and send it to me — paste it right into our chat — and I'll help
you figure out what it means and fix it. This is normal and expected to happen at least
once; that's the entire point of testing.

## Quick reference — the two commands you'll reuse most

| What you want | Command |
|---|---|
| Reset the demo account to a clean state | `python scripts/seed_demo_data.py` |
| Run every automated test and see results | `python -m unittest discover -s tests -t . -v` |

Both only work with `(venv)` showing at the start of your terminal line (Step 1) — if
you close the terminal and reopen it later, just redo Step 0 and Step 1 before running
either command again.
