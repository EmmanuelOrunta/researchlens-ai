# ResearchLens AI — Presentation Prep: Technical Q&A

*A study guide answering the 6 questions Emma asked, grounded in the actual codebase and the live database, for use while preparing to present.*

---

## 1. Can I see the data in the database? What type of database is this?

**What it is:** ResearchLens AI uses **SQLite** — a free, file-based relational database. There's no separate database server to install or run; the entire database is one file on disk: `database/researchlens.db`. This is a common and completely legitimate choice for a local prototype/capstone project — it's the same engine used inside browsers, phones, and countless production apps for exactly this kind of self-contained use case.

**What's actually in it right now** (queried live from the real file):

| Table | Rows | What it holds |
|---|---|---|
| `users` | 5 | Registered accounts |
| `research_projects` | 3 | Projects created across those accounts |
| `papers` | 16 | Papers pulled in from Semantic Scholar / OpenAlex searches |
| `saved_papers` | 14 | Links between a project and the papers saved into it |

The `users` table stores: `id`, `name`, `email`, `password_hash` (never the raw password — see Q3), and `created_at`. A real row looks like this:

```
(1, 'Emmanuel Orunta', 'emmanuelorunta@gmail.com',
 '$2b$12$kY9ebim0GJKtKiEOIwvdJOwpuIZDnRVELqUaXejNFOrxv140uwH4e',
 '2026-08-17 10:15:29.417848')
```

Note: if you open the raw `.db` file, you'll also see four unused columns on `users` (`is_verified`, `verification_code`, `verification_code_expires_at`, `verification_sent_at`). These are harmless leftovers from the email-verification feature that was built, tested, and then reverted (see Q2) — the app never reads or writes them anymore, but the columns physically persisted because SQLite doesn't automatically drop columns when you stop using them. It's fine to leave them or mention them if asked — it's a small, explainable footnote, not a bug.

**How to see it yourself, two ways:**

1. **GUI (recommended for a demo):** Download **[DB Browser for SQLite](https://sqlitebrowser.org/)** (free, Windows/Mac/Linux). Open `database/researchlens.db`, click "Browse Data," pick a table from the dropdown. This is the easiest way to *show* the data live during a presentation.
2. **Command line:** From the project folder, run `sqlite3 database/researchlens.db`, then at the `sqlite>` prompt: `.tables` to list tables, `.schema users` to see a table's structure, or `SELECT * FROM users;` to see rows.

Either way, you're looking at the exact same file the Flask app reads and writes through SQLAlchemy — there's no hidden copy or cache.

---

## 2. Why couldn't 2-step verification be implemented? How could it be done?

**What was attempted:** Full email-based verification — on registration, generate a 6-digit code, email it via Gmail SMTP (using a Gmail App Password), and block login until the code is entered.

**Why it failed:** Not a design flaw — an **environment-specific SSL/TLS problem** on the machine running the app. The exact error was:

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
Basic Constraints of CA cert not marked critical
```

This is a known issue on Windows with recent Python/OpenSSL 3.x versions: Python's `ssl` module validates the certificate chain against the certificates in the Windows OS certificate store, and on some Windows machines that store contains a root CA certificate (often injected by antivirus software doing "HTTPS scanning") that fails OpenSSL's stricter validation rules. It's not about the code being wrong or Gmail being unreachable — the SMTP connection to `smtp.gmail.com:587` was succeeding; it failed at the TLS handshake, specifically at certificate validation.

The fix that was identified (before the feature was reverted) was to make Python trust a **known-good, independent certificate bundle** — the `certifi` Python package — instead of asking Windows for one:

```python
import ssl, certifi
context = ssl.create_default_context(cafile=certifi.where())
```

This bypasses the flaky Windows cert store entirely by using Mozilla's curated CA bundle (which `certifi` packages and ships).

**Why it was reverted instead of debugged further:** given a capstone timeline, chasing an environment-specific SSL quirk wasn't worth the risk — the decision was to fall back to the stable, working registration flow (register → logged in immediately, no email step) rather than risk leaving the whole login flow broken close to a deadline. This is a defensible engineering call to explain in a presentation: *"we identified the root cause, had a fix, but prioritized stability given the timeline."*

**How it *could* be (re-)implemented**, in order of robustness:

1. **Apply the `certifi` fix above** and retry the original SMTP approach — this alone likely resolves it.
2. **Use a transactional email API instead of raw SMTP** (e.g., SendGrid, Mailgun, Amazon SES, Resend) — these use HTTPS/REST calls rather than raw SMTP+TLS sockets, which sidesteps this whole class of certificate issue and is also what real production apps typically use instead of a personal Gmail account.
3. **True "2-step verification" (2FA)**, as opposed to *email verification*, is actually a different and slightly bigger feature: a one-time code from an authenticator app (TOTP, via a library like `pyotp`) or an SMS code, entered at *every* login, not just at registration. What was built and reverted here was **email verification** (proving the email address is real, once, at signup) — worth being precise about this distinction if asked in a Q&A, since they're related but not identical security features.

---

## 3. How is the password protected? What's the security architecture?

**Hashing algorithm: bcrypt.** When a user registers or changes their password, the app never stores the plain-text password. Instead:

```python
bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
```

A real hash from the live database looks like this:

```
$2b$12$kY9ebim0GJKtKiEOIwvdJOwpuIZDnRVELqUaXejNFOrxv140uwH4e
```

Breaking that down: `$2b$` identifies the bcrypt algorithm version, `12` is the **cost factor** (bcrypt's default — it controls how computationally expensive each hash is to compute), and the rest is the salt + resulting hash combined.

**Why bcrypt specifically, and why this matters:**

- **Salting:** bcrypt automatically generates a random salt per password and bakes it into the output. That's why, even though several test accounts almost certainly used the same or similar passwords, every hash in the `users` table looks completely different. Without salting, two users with the same password would have identical hashes, which is a red flag for attackers and enables "rainbow table" lookups.
- **Deliberately slow:** unlike a fast hash like MD5 or SHA-256, bcrypt is designed to be computationally expensive on purpose. If someone stole the database file, they can't just hash millions of guessed passwords per second and compare — bcrypt's cost factor makes brute-forcing dramatically slower (this is the whole point of the "cost factor 12" — it's tunable to keep pace with faster hardware over time).
- **One-way:** there is no "decrypt" for a hash. Login works by re-hashing the *submitted* password with `bcrypt.checkpw()` and comparing the result to the stored hash — the original password is never recovered or compared directly, and it's never stored anywhere in log files, memory dumps, or elsewhere in the database.

**The rest of the security architecture, briefly:**

- **Session management:** After login, Flask sets a `user_id` in a signed session cookie, cryptographically signed using `FLASK_SECRET_KEY` (kept in an untracked `.env` file, not committed to source control). "Signed" means the cookie's contents can't be tampered with by the user's browser (Flask would detect and reject a modified cookie), though — important nuance if asked — a signed cookie is not *encrypted*; it's fine for something like a user ID, but nothing sensitive is stored in it.
- **Password rules enforced server-side** at registration and password-change (`get_password_error` in `auth_routes.py`): minimum 8 characters, plus a mix of uppercase, lowercase, a number, and a special character — reducing how many accounts would even be vulnerable to a fast dictionary attack in the first place.
- **Re-authentication for destructive actions:** both changing a password and deleting an account require re-entering the *current* password first (checked with the same `verify_password()`), so a stray click or someone at an unlocked, still-logged-in browser can't silently change or destroy an account.
- **Account deletion is a real, cascading delete**, not a soft "disabled" flag: deleting an account removes the row from `users` and cascades to delete that user's `research_projects` and their `saved_papers` links, freeing up the email address to be reused for a fresh registration — same idea as this account never existed.

This combination — bcrypt with salting for password storage, signed session cookies for auth state, and password confirmation gates on sensitive actions — is a standard, defensible security architecture for this kind of app, and one worth walking through explicitly in a presentation since a professor is very likely to ask "how do you handle passwords?"

---

## 4. Why was this tech stack better than Streamlit for the UI/UX?

**The original plan used Streamlit** — a Python framework that turns a single Python script into a reactive web app extremely quickly, with almost no HTML/CSS/JS needed. Great for fast internal tools and data-science dashboards.

**Its limitation for this project:** Streamlit trades away layout and styling control in exchange for that speed. It renders widgets top-to-bottom in a fairly fixed, opinionated visual style; deep custom CSS, custom multi-page navigation, split-screen layouts, and pixel-level design control are all difficult or unsupported. For a project whose brief explicitly cared about UI/UX (a polished login/register experience, a real sidebar-based app shell, a custom design system), Streamlit's rendering model becomes a ceiling rather than an accelerator.

**Why Flask instead:** Flask is a minimal web framework that gives full control over three things Streamlit abstracts away:

- **Routing:** every page (`/login`, `/dashboard`, `/projects/<id>`, `/settings`, etc.) is an explicit Flask route, organized into blueprints (`auth_bp`, `main_bp`, `papers_bp`, `settings_bp`) — one file per feature area, which also just makes the codebase easier for a 3-person team to divide and work on in parallel.
- **Templates (Jinja2):** real, hand-authored HTML pages that extend a shared `base_app.html` layout (the sidebar, top bar, flash messages), so every page shares one consistent shell without duplicating markup.
- **Static CSS/JS:** a genuine custom design system in `static/css/style.css` — custom fonts (Fraunces for headings, Inter for body text), a split-screen auth page design, pill-shaped buttons, a custom sidebar with active-state highlighting, card/panel components (including the new red-tinted "Danger Zone" panel for account deletion) — none of which would have been realistically achievable inside Streamlit's component model.

**What tech is used for what, concretely:**

| Layer | Technology | Role |
|---|---|---|
| Backend framework | Flask (Python) | Routing, request handling, blueprints |
| Templates | Jinja2 | Server-rendered HTML pages, shared layout |
| Styling | Hand-written CSS (`style.css`) | Custom design system, fonts, colors, components |
| Interactivity | Vanilla JavaScript (`app.js`) | Small enhancements: show/hide password, confirm-before-delete dialogs |
| Database | SQLite | Local, file-based data storage |
| ORM | SQLAlchemy | Python objects ↔ database rows, without hand-written SQL for most operations |
| Password security | bcrypt | Password hashing (see Q3) |
| External data | `requests` (HTTP client) | Calls to Semantic Scholar and OpenAlex APIs (see Q5) |

**One accuracy note worth flagging for your presentation:** the Sprint 2 deck's "Architecture Note" slide currently says the Streamlit → Flask pivot happened *"this sprint"* (i.e., during Sprint 2). Looking at the project's own `README.md`, it actually states the opposite — that the Flask build **is** the Sprint 1 deliverable, and that it *already* replaced the Streamlit prototype before Sprint 1 was submitted:

> *"This is the Sprint 1 build... This build replaces the earlier Streamlit prototype with a real HTML/CSS/JS frontend served by a Flask backend..."*

So the pivot happened at/before Sprint 1, not during Sprint 2. If a professor has seen the Sprint 1 submission, the deck's current wording could look like an inconsistency. Worth either correcting that one sentence on the deck before presenting, or simply not repeating the "this sprint" framing out loud when you present that slide — happy to fix the wording in the deck if you want a corrected version.

---

## 5. How does Paper Search work? What are Semantic Scholar and OpenAlex?

**What they are:** both are **free, public, official REST APIs** — not scraped websites, not unofficial workarounds. A "REST API" just means another organization's server that you can send an HTTP request to (the same way a browser loads a webpage) and get back structured data (JSON) instead of a rendered page. No login or scraping involved — this is the intended, sanctioned way to programmatically access their data.

- **Semantic Scholar** — built by the Allen Institute for AI (AI2). A free academic search API covering hundreds of millions of papers, with rich metadata (title, authors, year, abstract, DOI, external IDs). No API key required for light/free use (an optional key just raises the rate limit).
- **OpenAlex** — a fully open, free scholarly index (successor to the earlier Microsoft Academic Graph). Also no key or signup required. Its abstracts come back in an unusual format called an "inverted index" (a word → position map, to save space) — the app reconstructs the plain-text abstract from it (`_rebuild_abstract()` in `openalex_service.py`).

Are they "like Google Scholar"? In *purpose*, yes — both are academic search engines. In *mechanism*, no: Google Scholar is a website meant to be browsed by a human in a browser, with no official API (see Q6). Semantic Scholar and OpenAlex are the API-first equivalent — built specifically for other software to query programmatically.

**How search actually works in the app, end to end:**

1. User types a query on the search page for a project.
2. The route (`routes/papers_routes.py`) calls **both** `semantic_scholar_service.search_papers()` and `openalex_service.search_papers()` — each independently fetches up to `SEARCH_FETCH_LIMIT_PER_SOURCE = 30` results.
3. Results are **merged and de-duplicated** — the same paper often exists in both sources, so results are matched first by DOI (the most reliable unique identifier for an academic paper), falling back to a normalized/lowercased title comparison if there's no DOI, so the user doesn't see the same paper twice.
4. Results can be **filtered by year** (single year or a custom range, e.g. 2022–2026) and **sorted** (relevance / newest / oldest), all handled server-side in `_filter_by_year()` / `_sort_results()`.
5. Results are **paginated** at `SEARCH_PAGE_SIZE = 10` per page, so a search that returns dozens of merged results doesn't dump them all on one screen.
6. If one source is down or rate-limited, the other still returns results — OpenAlex functions as a working fallback for Semantic Scholar and vice versa, so a single flaky API doesn't take down search entirely.

**Why these two, specifically:** both are free, require no paid tier or approval process, have generous rate limits for a student project's traffic volume, and — critically — are explicitly built and licensed for exactly this kind of programmatic access, which ties directly into the answer for Q6.

---

## 6. Why wasn't Google Scholar used?

**In short: Google Scholar has no official public API.** Google has never released one, despite it being one of the most requested features from researchers and developers for over a decade.

The only ways to get data out of Google Scholar programmatically are:

1. **Web scraping** — writing code that pretends to be a browser, fetches the HTML search-results page, and parses it. This directly violates Google's [Terms of Service](https://policies.google.com/terms), and Google actively detects and blocks this kind of automated traffic (CAPTCHAs, IP bans) specifically to prevent it.
2. **Third-party paid scraping services** (e.g., SerpApi) that do the scraping *for* you, behind a paid subscription, and reformat the result as if it were an API. This still relies on scraping under the hood — it's just outsourced — and adds an ongoing cost that isn't appropriate for a free student capstone project.

Neither option is something a legitimate, ToS-compliant academic project should build on — using it risks the whole search feature breaking without warning (if Google changes their page layout or tightens blocking) or, worse, could be seen as violating terms of service in an academic evaluation context.

**Semantic Scholar and OpenAlex exist precisely to fill that gap** — they were built by organizations (the Allen Institute for AI, and the OpenAlex/OurResearch team respectively) specifically to give researchers and developers free, legal, stable programmatic access to scholarly data, which is exactly what Google Scholar deliberately does not offer. Between the two of them, they cover a very large share of the same underlying academic literature Google Scholar indexes — so functionally, the project isn't really giving up coverage, just swapping an unofficial, ToS-violating path for two official, sanctioned ones (with the added benefit of redundancy, per Q5, since it now has two independent sources instead of one).

**One-line version for your presentation, if asked:** *"Google Scholar doesn't offer a public API, so building on it would mean scraping their website, which violates their Terms of Service and can be blocked at any time. Semantic Scholar and OpenAlex are free, official APIs built specifically for this kind of use, and together they cover a comparable body of academic literature."*
