# Final Manual Testing Checklist

*A feature-by-feature pass for the whole team to run through together before the
Assessment 2 presentation — this is different from `Sprint5_Usability_Testing_Script.md`
(which watches a brand-new user discover the app for the first time) and
`Sprint5_AI_Accuracy_Checklist.md` (which judges whether AI answers are factually
correct). This one just asks: does every feature, including every edge case, actually
work, right now, on the version you're about to submit and present?*

## How to use this

- Split the sections below across the team — you don't all need to run every row,
  but every row should get run by *someone* before presentation day.
- Use a **real test account you register yourself** for most sections — not the demo
  account (`demo@researchlens.ai`), and not an account with data you care about,
  since a few rows here deliberately test deletion. The Mobile section is the one
  exception: the demo account's pre-filled data is actually convenient there.
- Mark each row ✅ Pass, ❌ Fail, or ⚠️ Works, but worth a look before you check it off.
  Anything ❌ or ⚠️ goes straight into `Sprint5_Plan.md`'s bug table (item 7) with
  who found it and when.
- Run this on the exact code you're about to submit — not an older version, not a
  version with uncommitted local changes.

---

## A. Accounts & authentication

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| A1 | Register a new account with a valid name/email/password → lands straight on the Dashboard | | | |
| A2 | Register again with the **same email** → rejected with an "already exists" message, no duplicate account created | | | |
| A3 | Register with a weak password (e.g. all lowercase, no number) → rejected with a specific message, not a generic one | | | |
| A4 | Register with a confirm-password that doesn't match → rejected, account not created | | | |
| A5 | Log in with the correct email + password → succeeds | | | |
| A6 | Log in with the correct email + **wrong** password → rejected with "Incorrect email or password" | | | |
| A7 | Log in with an email that **doesn't exist at all** → rejected with the exact same message as A6 (this is the user-enumeration check — the two errors must be indistinguishable) | | | |
| A8 | While signed out, try to open a workspace URL directly (e.g. Dashboard) → redirected to `/login`, not shown the page | | | |
| A9 | Log out → then try the back button or a saved workspace link → still redirected to `/login`, not shown a cached page | | | |

## B. Dashboard

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| B1 | Stat cards (Research Projects / Saved Papers / Papers Analysed / Papers Synthesized) match what's actually in your account | | | |
| B2 | "Recently viewed projects" lists real projects and each link opens the right one | | | |
| B3 | "New Research Project" quick action opens the create-project form | | | |
| B4 | "Search Papers" and "My Papers" quick actions both go to the right page | | | |
| B5 | Dark mode toggle switches the whole app's palette, and it's still dark after a full page reload | | | |

## C. Project management

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| C1 | Create a project with a title, research question, field, and keywords → all fields save and display correctly | | | |
| C2 | Edit that project's details → changes save | | | |
| C3 | Open "My Projects" → the new project is listed | | | |
| C4 | Delete a **disposable test project** → it disappears, and its saved papers/notes/chat go with it (don't do this to a project you want to keep) | | | |

## D. Academic search

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| D1 | Search a common topic → results appear, with a "Showing results from…" line naming both sources | | | |
| D2 | Apply a year-from / year-to filter → every result shown falls inside that range | | | |
| D3 | Change "Sort by" (relevance / newest / oldest) → the order of results actually changes | | | |
| D4 | Search something broad enough to return 15+ results → pagination controls appear and work | | | |
| D5 | Save a paper to a project → it appears in that project's saved papers | | | |
| D6 | Search for the same paper again (or search two ways that would both surface it) → it isn't saved twice / is clearly marked already-saved | | | |
| D7 | Upload a real PDF directly → it's saved with its text extracted (check its detail page has real extracted text, not blank) | | | |
| D8 | Upload a non-PDF file or a corrupted file → rejected with a clear message, not a crash **(boundary case)** | | | |
| D9 | Temporarily rename `SEMANTIC_SCHOLAR_API_KEY` in `.env` to something invalid, restart, search again → results still come back via OpenAlex alone, with a visible warning **(boundary case — put the real key back afterward)** | | | |

## E. My Papers & AI Paper Analysis hub

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| E1 | "My Papers" lists every paper you've saved, across every project | | | |
| E2 | "AI Paper Analysis" hub shows every saved paper, which project(s) it's in, and whether it's been analyzed | | | |

## F. AI Summary *(needs `OPENAI_API_KEY` set for the Pass rows)*

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| F1 | Generate an AI Summary for a saved paper → streams in live, as six distinct paragraphs | | | |
| F2 | Evidence chips appear under the summary; clicking one shows the quote, verified/unverified, and a "View paper →" link | | | |
| F3 | Regenerate the summary on the same paper → it updates | | | |
| F4 | Temporarily remove/rename `OPENAI_API_KEY`, restart, try to generate a summary → clean message ("Add a free OPENAI_API_KEY in .env…"), not a crash or a frozen page **(boundary case — put the real key back afterward)** | | | |

## G. Relevance Analysis

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| G1 | Generate a relevance analysis for a saved paper → streams in with a 1–5 rating and written reasoning | | | |
| G2 | The reasoning given actually matches the number given (not a 5/5 with lukewarm reasoning, etc.) | | | |

## H. Literature Matrix

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| H1 | "Extract with AI" on a saved paper → Methodology / Sample / Findings / Limitations all populate | | | |
| H2 | Manually edit one of those cells by hand → saves and displays correctly | | | |
| H3 | A paper never extracted shows clean blank cells, not an error | | | |
| H4 | Export to **Excel** → file opens, data matches what's on screen | | | |
| H5 | Export to **PDF** → file opens, data matches what's on screen | | | |
| H6 | Export to **Word** → file opens, data matches what's on screen | | | |

## I. Paper Synthesis

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| I1 | Select 2+ saved papers → generate a synthesis → a flowing, multi-paragraph narrative streams in | | | |
| I2 | Evidence chips appear and are clickable, same as AI Summary | | | |
| I3 | Try to generate with **only 1 paper selected** → blocked with a clear "need at least 2" message, not a crash **(boundary case)** | | | |
| I4 | Try to generate with **0 papers selected** → same clean rejection **(boundary case)** | | | |

## J. Ask the Literature

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| J1 | Ask a real question about your saved papers → a streamed answer appears with citation chips | | | |
| J2 | Ask a natural follow-up (using "it"/"that") → the answer correctly understands what you mean from the previous turn | | | |
| J3 | Edit an earlier question and resend → everything asked after it is discarded and a fresh answer generates | | | |
| J4 | Submit a **blank** question → rejected cleanly, no empty message sent **(boundary case)** | | | |
| J5 | Try this in a project with **zero saved papers** → clear "save at least one paper first" message **(boundary case)** | | | |

## K. Notes

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| K1 | Add a note (with and without a title) to a saved paper | | | |
| K2 | Edit an existing note | | | |
| K3 | Delete a note | | | |

## L. Settings

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| L1 | Update your display name → saves, shows correctly everywhere (dashboard greeting, topbar, avatar initials) | | | |
| L2 | Change your password (with the correct current password) → saves; log out and back in with the new password to confirm | | | |
| L3 | Try to change your password with the **wrong** current password → rejected **(boundary case)** | | | |
| L4 | Delete-account flow, on a **throwaway test account only** → asks for password confirmation, then actually removes the account and its data | | | |

## M. Mobile & responsive *(the new hamburger-menu nav)*

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| M1 | On a phone (or a browser resized under ~720px wide), the sidebar is gone and a small bar with the logo + hamburger icon appears instead | | | |
| M2 | Tapping the hamburger slides the full nav in from the left with a dimmed backdrop behind it, and the icon becomes an ✕ | | | |
| M3 | Tapping the dimmed backdrop closes the drawer again | | | |
| M4 | Tapping a link inside the drawer navigates to that page normally | | | |
| M5 | On a laptop/desktop-width screen, confirm the sidebar still looks and behaves exactly as before — no hamburger, no drawer | | | |

## N. Cross-cutting security check

| # | Check | Pass/Fail | Tester | Notes |
|---|---|---|---|---|
| N1 | While signed in as Account A, try editing a project/paper URL to point at an id that belongs to Account B → blocked, not shown **(boundary case)** | | | |

---

## Sign-off

Once every row above has a tester and a result, fill in the summary so whoever's
presenting knows where things stand without re-reading the whole table:

| Section | All rows run? | Any ❌ still open? |
|---|---|---|
| A. Accounts & authentication | | |
| B. Dashboard | | |
| C. Project management | | |
| D. Academic search | | |
| E. My Papers / AI Analysis hub | | |
| F. AI Summary | | |
| G. Relevance Analysis | | |
| H. Literature Matrix | | |
| I. Paper Synthesis | | |
| J. Ask the Literature | | |
| K. Notes | | |
| L. Settings | | |
| M. Mobile & responsive | | |
| N. Security check | | |

Any row left ❌ right up to presentation day should become a named limitation you're
ready to speak to honestly — not a surprise a judge finds for you live.
