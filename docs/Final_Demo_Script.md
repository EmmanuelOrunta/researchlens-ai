# Final Presentation — Demo Mode Run-of-Show

*What to actually click through during the live prototype demonstration, using the
`demo@researchlens.ai` account from `scripts/seed_demo_data.py`. Built to directly match
what the assessment guide asks for: the main workflow end to end, a successful case AND
a boundary case, and no confidential data on screen — see
`docs/Sprint5_Note_1_Demo_Mode.md` for how Demo Mode itself works under the hood.*

## Before you walk in the room

- [ ] Re-run `python scripts/seed_demo_data.py` **on the laptop you're presenting
      from**, the morning of (or right before) presenting — it always wipes and
      rebuilds a clean demo project, so this erases any mess from earlier rehearsals.
- [ ] Do one full walkthrough on that same laptop **with WiFi off**, to confirm nothing
      on the core path below unexpectedly needs a network call.
- [ ] Confirm `OPENAI_API_KEY` is set normally (not the boundary-case state) before you
      start, unless you're deliberately opening with the boundary case.
- [ ] Have a backup ready in case live demo isn't possible: a short screen-recording of
      this exact walkthrough, or the screenshots already in `docs/screenshots/`. The
      guide requires this — don't skip it.
- [ ] Log in as `demo@researchlens.ai` / `DemoDay2026!` and have the Dashboard open and
      waiting before you start talking.
- [ ] This app has a single user role (a signed-in researcher) — there's no separate
      admin/reviewer role to demonstrate, so the walkthrough below covers that one
      role's complete journey, beginning to end, which is what the guide asks for.

## Suggested timing

A full 30/40-minute slot has to cover slides, demo, reflection, and questions — treat
the live demo itself as roughly **6–8 minutes**, not the whole slot. Everything below is
ordered so you can cut from the bottom if you're running long; the first five steps are
the ones to never skip.

## The walkthrough

1. **Dashboard** — "This is Demo Presenter's account, already set up with a real
   project." Point out the stat cards (1 project, 5 saved papers, 1 analysed, 1
   synthesized) and the "Generative AI in Higher Education" project under Recently
   Viewed.

2. **Open the project → saved papers** — five real papers: Chan (2023), Schwarz
   (2025), Okafor (2024), Park (2024), Dubois (2025). Mention this is the same dataset
   used throughout the README and the presentation deck, so everything shown is
   consistent.

3. **Open Chan (2023) → AI Summary** — the six-paragraph structured summary is already
   there. Click into one of its evidence chips and show it expand: quote, "Verified
   against the saved paper," and a link back to the paper. **This is your successful
   case.**

4. **Literature Matrix** — show all five rows. Three (Chan, Schwarz, Park) already have
   Methodology / Sample / Findings / Limitations filled in; Okafor and Dubois are
   deliberately blank, exactly like a freshly-saved paper. If WiFi and your API key are
   genuinely working, click "Extract with AI" on one of the blank ones live — a real,
   unscripted bonus moment. If you're not confident in the room's WiFi, skip this and
   say so plainly rather than risk it hanging.

5. **Paper Synthesis** — open the existing synthesis across Chan, Schwarz, and Park.
   Expand the Schwarz (2025) chip (verified, green) and the Chan and Hu (2023) chip
   (unverified, amber) side by side. **This is your boundary/validation case** — say
   out loud that the amber one isn't hidden or treated as a failure, it's the system
   being honest that it couldn't confirm that particular quote word-for-word.

6. **Ask the Literature** — scroll the existing two-turn conversation about ChatGPT in
   statistics education. If time and your API key allow, ask one genuinely new
   question live to show the streaming answer appear in real time; if not, the
   existing conversation already demonstrates the feature fully.

7. *(Optional, only if you've rehearsed it)* **Show the missing-key boundary case on
   purpose.** In a second terminal, stop the app, temporarily comment out
   `OPENAI_API_KEY` in `.env`, restart, and click "Generate AI Summary" on any paper —
   the app replies with one plain sentence ("Add a free OPENAI_API_KEY in .env to use
   AI analysis…") instead of crashing or freezing. Put the real key back and restart
   before continuing. Only do this live if you've practiced the exact steps — it's a
   strong moment when it goes smoothly and a distraction if it doesn't. The amber
   evidence chip in step 5 already satisfies the guide's "boundary case" requirement
   on its own, so this step is a bonus, never a requirement.

8. *(Optional, if someone asks or time allows)* **Pull out a phone** and show the
   hamburger-menu nav from the recent mobile update — tap it open, tap the backdrop to
   close it. Good to have ready for a question, not worth scripting into the main flow.

## What NOT to do live

- Don't demo on your **real personal account** — stick to Demo Mode or a disposable
  test account, never anything with content you wouldn't want on a shared screen.
- Don't attempt the Semantic Scholar key-swap or account-deletion boundary cases from
  the manual testing checklist live — those belong in testing, not presenting.
- Don't read the slides out loud while the app is open — the slides are there to cue
  what you're about to show, not to be read verbatim (the assessment guide says this
  explicitly).

## If something breaks mid-demo

Say so plainly, switch to the backup video or screenshots, and keep going — the guide
explicitly expects a backup plan to exist for exactly this reason. A smooth recovery
reads better than pretending nothing went wrong.
