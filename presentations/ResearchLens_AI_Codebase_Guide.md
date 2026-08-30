# ResearchLens AI — Codebase Walkthrough

*Every folder and file in the project, what it's for, and what it contains. Written for presentation prep — pairs with `ResearchLens_AI_Presentation_QA_Guide.md`.*

---

## The big picture: how the folders relate

The project follows a standard **layered architecture** — a common, deliberate pattern for keeping a Flask app organized as it grows, and a good thing to name explicitly if asked about design decisions:

```
templates/   → the VIEWS      (what the user sees — HTML pages)
static/      → the ASSETS     (CSS styling, small JS interactions)
routes/      → the CONTROLLERS (handle web requests, decide what to do, call services)
services/    → the BUSINESS LOGIC (the actual rules — validation, hashing, search merging)
models/      → the DATA       (table definitions — the shape of what's stored)
database/    → the STORAGE    (the actual SQLite file on disk)
```

The rule the codebase follows consistently: a **route** never talks to the database directly — it calls a **service** function, which is the only thing that touches a **model**. This is why, for example, `routes/settings_routes.py` calls `auth_service.delete_user()` instead of writing `session.delete(user)` itself — it keeps validation/business-rules in one place instead of scattered across every route that happens to need them.

---

## Root-level files

**`app.py`** — the entry point; running `python app.py` starts the whole app. It creates the Flask app object, sets the session-cookie secret key from `.env`, sets a 20MB cap on file uploads, calls `init_db()` to create the database on first run, and registers the four blueprints (`auth`, `main`, `papers`, `settings`) so their routes become active. It also defines two things every template can use: the `initials` filter (turns "Emma Nakamura" into "EN" for the avatar) and a `context_processor` that makes `current_user` available in every template automatically, so `base_app.html` can show the signed-in user's name/email without every single route passing it in by hand.

**`requirements.txt`** — the list of Python packages the project depends on: `Flask` (web framework), `SQLAlchemy` (ORM), `bcrypt` (password hashing), `python-dotenv` (loads `.env`), `requests` (HTTP client for the two paper-search APIs), `PyMuPDF` (reads text out of uploaded PDFs). Running `pip install -r requirements.txt` installs all of them at once.

**`.env.example`** — a template for the real `.env` file (which is never committed to git, since it holds secrets). Documents three variables: `FLASK_SECRET_KEY` (signs session cookies — see the Q&A guide's security section), `OPENAI_API_KEY` (not used yet — reserved for Sprint 3's AI features), `SEMANTIC_SCHOLAR_API_KEY` (optional, raises the free rate limit).

**`.gitignore`** — tells git which files/folders to never track: Python cache files, the virtual environment, `.env` (secrets), the actual `database/*.db` file (each teammate's local data shouldn't overwrite a teammate's when pulling), and uploaded PDFs (user content, not source code).

**`README.md`** — setup instructions for a new teammate: installing Python/VS Code, creating a virtual environment, installing dependencies, running the app. Also states up front that this Flask build **is** the Sprint 1 deliverable and already replaced an earlier Streamlit prototype (relevant to the Q4 timeline note in the Q&A guide).

---

## `models/` — the data layer

Each file defines one database table as a Python class (a SQLAlchemy "model"). These are pure data definitions — no logic about *when* to create or delete a row lives here, only *what a row looks like*.

- **`user.py`** — the `users` table: `id`, `name`, `email` (unique), `password_hash`, `created_at`. The comment on `password_hash` is blunt about it on purpose: *"never store the raw password!"*
- **`project.py`** — the `research_projects` table: one row per project a user creates (`title`, `research_question`, `research_field`, `keywords`), linked to its owner via `user_id` (a foreign key into `users`). Also has `last_viewed_at`, which powers the dashboard's "Recently viewed" list.
- **`paper.py`** — the `papers` table: a paper found via search or uploaded as a PDF. `source` records which ("semantic_scholar", "openalex", or "upload"); `external_id` stores the source API's own ID (used to avoid saving the same paper twice); `file_path`/`extracted_text` are only filled in for uploaded PDFs.
- **`saved_paper.py`** — the `saved_papers` table: a pure join table linking a `paper_id` to a `project_id`. This is what lets the *same* paper be saved into more than one project without duplicating the paper's own row.
- **`__init__.py`** — empty; its only job is telling Python "this folder is a package" so `from models.user import User` works elsewhere.

---

## `routes/` — the controllers (one blueprint per feature area)

Each file is a Flask **Blueprint**: a named group of URL routes. Splitting them this way (rather than one giant `app.py`) is exactly what let a 3-person team divide the work without constantly editing the same file.

- **`auth_routes.py`** (`auth_bp`) — registration, login, logout. `/login` and `/register` each handle both a GET (show the empty form) and a POST (validate the submitted fields one by one — email format via a regex, password complexity via `get_password_error()` — and either re-show the form with inline red error messages, or create the account/verify the password and log the user in). `/logout` clears the session.
- **`main_routes.py`** (`main_bp`) — the dashboard and the research-project CRUD screens (create/read/update/delete). Defines the `login_required` decorator used across the app — it wraps a view function and bounces anyone without `session["user_id"]` back to the login page before the view even runs. `project_detail()` is also where `mark_project_viewed()` gets called, updating "last viewed" for the dashboard.
- **`papers_routes.py`** (`papers_bp`) — the biggest route file (~420 lines): searching both APIs, merging/de-duplicating/filtering/sorting/paginating results, saving a result into a project, uploading a PDF directly, viewing a saved paper, and the global "My Papers" page across all projects. `_search_academic_sources()` is the core search-orchestration function referenced in the Q&A guide's Q5 answer.
- **`settings_routes.py`** (`settings_bp`) — the Settings page: viewing it, updating your display name, updating your password (requires the current password first), and the account-deletion route added most recently (also requires the current password, then calls `project_service.delete_all_projects_for_user()` followed by `auth_service.delete_user()` before clearing the session).
- **`__init__.py`** — empty package marker, same role as `models/__init__.py`.

---

## `services/` — the business logic

This is where the actual *rules* live — the layer routes call into rather than duplicating logic themselves.

- **`database_service.py`** — sets up the SQLite connection (`engine`), the session factory (`SessionLocal`/`get_session()`), and the shared `Base` class every model inherits from. `init_db()` creates all tables on first run; `_apply_lightweight_migrations()` is a hand-rolled, minimal substitute for a real migration tool (like Alembic) — since this is a local prototype, it just checks with `PRAGMA table_info` whether a newly-added column (`last_viewed_at`) already exists on disk and adds it via `ALTER TABLE` if not, so nobody has to delete their database file every time the schema changes slightly.
- **`auth_service.py`** — password hashing/checking (`hash_password`, `verify_password`, wrapping `bcrypt`) and the basic User CRUD operations routes call into: `get_user_by_email`, `get_user_by_id`, `create_user`, `update_user_name`, `update_user_password`, and `delete_user` (added for account deletion — a plain `session.delete(user); session.commit()`, with the comment noting the caller is responsible for wiping the user's owned data *first*).
- **`project_service.py`** — everything about a research project's lifecycle: `create_project`, `get_projects_for_user`, `get_project_for_user` (critically, this one filters by *both* project id *and* the requesting user's id — that's what stops User A from viewing User B's project just by guessing a different number in the URL), `get_recent_projects_for_user` (the dashboard's "recently viewed" query), `mark_project_viewed`, `update_project`, `delete_project`, and `delete_all_projects_for_user` (the bulk cascade-delete used by account deletion).
- **`paper_service.py`** — turning a search result or an uploaded PDF into a `Paper` row, and managing which papers are saved to which project: `create_paper_from_search_result`, `create_uploaded_paper`, `save_paper_to_project`, `remove_paper_from_project`, `get_saved_papers_for_project`, plus access-control helpers like `user_can_access_paper()` (stops one user from viewing or downloading another user's uploaded PDF by guessing a paper ID).
- **`pdf_service.py`** — handles uploaded PDFs specifically: `is_allowed_pdf()` (checks the file extension), `save_uploaded_pdf()` (saves it to `uploads/` under a random UUID filename so two people's "paper.pdf" never collide), and `extract_text_from_pdf()` (uses PyMuPDF to pull out plain text, capped at 200,000 characters, so a later AI-analysis feature has something to read — returns an empty string rather than crashing if the PDF is a scanned image with no selectable text).
- **`semantic_scholar_service.py`** and **`openalex_service.py`** — the two external API clients described in the Q&A guide's Q5. Each exposes one function, `search_papers(query, limit)`, that calls the respective REST API via `requests`, normalizes the JSON response into the same dict shape (`title`, `authors`, `year`, `abstract`, `doi`, `url`, `external_id`), and returns `None` (not an empty list) specifically when the request fails outright, so the calling route can tell "zero results" apart from "couldn't reach the API."
- **`__init__.py`** — empty package marker.

---

## `templates/` — the views (Jinja2 HTML)

Two "base" layouts that every other page extends, plus one template per screen.

**Layouts:**
- **`base_app.html`** — the shell for every logged-in page: the left sidebar (Dashboard / My Projects / Search Papers / My Papers / the "Soon"-badged Analysis section / Settings), the top bar (signed-in user's name, email, avatar initials, sign-out button), and the flash-message area. Every other authenticated page's content drops into its `{% block content %}`.
- **`base_auth.html`** — the shell for the login/register screens: a split-screen layout, form on the left, a decorative "Potential Research Gap" preview card on the right (a preview of what a later sprint's research-gap feature will look like).

**Auth pages:** `login.html`, `register.html` — each just a form inside `base_auth.html`'s content block, with inline error messages next to whichever field failed validation, and a show/hide toggle on password fields.

**Workspace pages:** `dashboard.html` (stat cards + recently-viewed projects + quick actions), `projects.html` (grid of every project, with edit/delete), `new_project.html` / `edit_project.html` (the same form shape, reused for create vs. update), `project_detail.html` (one project's overview: research question, first 3 saved papers, and placeholder cards for Sprint 3/4 features like AI Analyses and the Literature Matrix — visibly marked "Soon").

**Papers pages:** `choose_project_for_search` uses `choose_project.html` (only shown if you have more than one project); `paper_search.html` (the search form with year-range filters and a sort dropdown, results list, and pagination — the template referenced in the Q&A guide's Q5 answer); `project_papers.html` (one project's full saved-papers list); `paper_detail.html` (a single paper's abstract/extracted text and which project(s) it's saved to); `my_papers.html` (every paper across all of a user's projects).

**`settings.html`** — Profile card (change name), Security card (change password), and the Danger Zone panel added most recently (delete account, gated behind re-entering your current password, with a JS confirm dialog as a first speed bump before the request is even sent).

---

## `static/` — CSS and JavaScript

- **`css/style.css`** — the entire hand-written design system in one file: custom fonts (Fraunces for headings, Inter for body text), the color palette, the sidebar/topbar layout, form fields and inline error styling, stat cards, project/paper cards, the split-screen auth page, and the red-tinted `.panel-danger` variant added for the account-deletion section. This is the concrete evidence for the Q4 answer about why Flask's static-CSS control mattered — none of this level of custom styling would be realistic inside Streamlit's component model.
- **`js/app.js`** — small, dependency-free interactivity: the password show/hide toggle, the `confirm-delete` handler (any form with `class="confirm-delete"` gets a native browser confirm dialog before submitting, driven by that form's `data-confirm="..."` text — reused for both project deletion and account deletion), and auto-dismissing flash messages after 4 seconds.

---

## The remaining folders

- **`database/`** — holds the single SQLite file, `researchlens.db`. Not committed to git (each teammate has their own local data) — see Q1 in the Q&A guide for how to browse it and what's really inside it right now.
- **`uploads/`** — where PDFs uploaded through the "Upload a PDF" form actually get saved on disk, under randomly generated filenames (e.g. `4b94684c357945328582fa99f6137ec9.pdf`) so two different users' files never collide or overwrite each other. Also git-ignored, aside from a placeholder `.gitkeep` so the empty folder still exists after a fresh clone.
- **`data/`** — currently just a placeholder (`.gitkeep`) with nothing else in it yet; reserved for data Sprint 3's AI-analysis features will need (e.g. cached embeddings or extracted-text indexes), not used by anything today.
- **`presentations/`** — not application code — this is where the Sprint 2 update deck and both of these study guides live, for convenience.

---

## One thread worth calling out in a presentation

Notice how the same small set of design decisions repeats everywhere: every "delete" cascades its child rows first (`delete_project` removes its `SavedPaper` rows before the project; `delete_all_projects_for_user` does the same at bulk scale for account deletion); every "get one thing" query for the workspace pages filters by the *owning user's id*, not just the record's own id (`get_project_for_user`, `user_can_access_paper`), which is what stops one account from reading or guessing into another account's data; and every destructive action in Settings re-checks the current password first. None of that is one big security feature — it's the same small, consistent habit applied everywhere, which tends to read well in a presentation as evidence of a deliberate architecture rather than one-off patches.
