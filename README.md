# ResearchLens AI (Flask + HTML/CSS/JS build)

An AI-assisted academic research workspace. Users can register and sign in, create
research projects, search academic literature across two scholarly APIs, save papers to
a project (or upload their own PDFs), and get AI-generated summaries, relevance
analysis, and multi-note annotations for each saved paper - all inside one consistent
Flask app.

This README covers everything shipped through **Sprint 3**:

- **Sprint 1 - Foundation & Authentication:** registration, login/logout, dashboard,
  research-project management, account settings, account deletion.
- **Sprint 2 - Academic Research Discovery:** combined Semantic Scholar + OpenAlex
  search, year filtering and sorting, saving papers to a project, direct PDF upload,
  and the full visual redesign (this build's real HTML/CSS/JS frontend, replacing the
  original Streamlit prototype before Sprint 1 was submitted).
- **Sprint 3 - AI Paper Analysis:** OpenAI-powered paper summaries and relevance
  analysis with live streaming output, a per-paper detail page, the "AI Paper
  Analysis" hub page across every saved paper, and a multi-note system for saved
  papers.

Still to come (see [section 9](#9-whats-next)): the literature comparison matrix,
"Ask Your Literature" (RAG-based Q&A), and research-gap detection.

---

## 1. Install the tools (one-time setup)

If you already have Python and VS Code installed (with the Python extension), skip to
section 2.

### Install Python
1. Go to [python.org/downloads](https://www.python.org/downloads/) and download Python 3.11 or later.
2. Run the installer. **On Windows, tick "Add Python to PATH" before clicking Install.**
3. Check it worked: open a terminal and run `python --version`.

### Install VS Code
1. Download from [code.visualstudio.com](https://code.visualstudio.com/).
2. Install the **Python** extension (by Microsoft) from the Extensions panel (`Ctrl+Shift+X`).

---

## 2. Open the project in VS Code

1. **File → Open Folder...** and select this `researchlens-ai-flask` folder.
2. Open a terminal: **Terminal → New Terminal** (or `` Ctrl+` ``).

---

## 3. Create a virtual environment

```
python -m venv venv
```

**Activate it:**

- Windows (PowerShell):
  ```
  venv\Scripts\Activate.ps1
  ```
  If PowerShell blocks this, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
  once (type `Y` when asked), then try again.
- Mac / Linux:
  ```
  source venv/bin/activate
  ```

Your terminal prompt should now start with `(venv)`. You'll need to activate the venv
again every time you open a new terminal to work on this project.

---

## 4. Install the project's dependencies

```
pip install -r requirements.txt
```

This installs Flask, SQLAlchemy, bcrypt, python-dotenv, requests, PyMuPDF (PDF text
extraction), and the `openai` client (Sprint 3's AI features).

---

## 5. Set up your API keys (needed for search and AI features)

Copy `.env.example` to a new file named `.env` in the project root, then fill in:

- **`FLASK_SECRET_KEY`** - any long random string, used to sign login session cookies.
  Generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- **`OPENAI_API_KEY`** - required for the AI Summary and Relevance Analysis features
  (Sprint 3). Get one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
  Without a key, those buttons show an "Add an OpenAI key" message instead of failing
  silently - the rest of the app works fine without it.
- **`SEMANTIC_SCHOLAR_API_KEY`** - optional. Paper search works without it (OpenAlex
  needs no key at all), but a free key raises Semantic Scholar's rate limit above the
  shared, unauthenticated pool. Request one at
  [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api#api-key).

`.env` is git-ignored, so your keys are never committed.

---

## 6. Run the app

```
python app.py
```

You'll see output ending in something like `Running on http://127.0.0.1:5000`. Open
that address in your browser - you should see the ResearchLens AI login screen.

Try it out:
1. Click **Create one** (register), fill in the form, submit.
2. You'll land on the Dashboard, signed in.
3. Click **+ New Research Project**, create one, see it appear on your dashboard.
4. Open the project, click **Search Papers**, search for a topic, and save a result
   to the project (or upload a PDF instead).
5. Open a saved paper and click **Generate AI Summary** or **Analyze Relevance**
   (requires an OpenAI key) to watch the analysis stream in live, then add a note.
6. Click **Sign out**, then log back in with the same email/password.

To stop the app: click the terminal and press `Ctrl+C`.

---

## 7. How the code is organised

```
researchlens-ai-flask/
├── app.py                        ← entry point: run this file. Creates the Flask app,
│                                    registers all four blueprints, sets up the
│                                    `initials` template filter and the `current_user`
│                                    context processor.
├── routes/                       ← controllers: handle requests, call services
│   ├── auth_routes.py             ← /login, /register, /logout
│   ├── main_routes.py             ← / (dashboard), research-project CRUD
│   ├── papers_routes.py           ← search, save/remove, PDF upload, My Papers,
│   │                                 paper detail pages, the AI Analysis hub, the
│   │                                 AI summary/relevance streaming endpoints, and
│   │                                 the multi-note endpoints (add/edit/delete)
│   └── settings_routes.py         ← Settings page: name/password change, account deletion
├── services/                     ← business logic, the only layer that touches models
│   ├── database_service.py        ← database connection, session factory, init_db()
│   ├── auth_service.py            ← password hashing (bcrypt), user CRUD
│   ├── project_service.py         ← research-project CRUD, "recently viewed"
│   ├── paper_service.py           ← saving/removing papers, access control, and the
│   │                                 multi-note functions (create/update/delete/list)
│   ├── pdf_service.py             ← validating and saving uploaded PDFs, text
│   │                                 extraction via PyMuPDF
│   ├── semantic_scholar_service.py ← Semantic Scholar API client
│   ├── openalex_service.py        ← OpenAlex API client (rebuilds abstracts from
│   │                                 their "inverted index" format)
│   └── openai_service.py          ← OpenAI Responses API integration: streams the
│                                     AI Summary and Relevance Analysis back to the
│                                     browser as they're generated
├── models/                       ← one file per database table
│   ├── user.py
│   ├── project.py
│   ├── paper.py                   ← a paper found via search or uploaded as a PDF
│   ├── saved_paper.py             ← join table: which paper is saved to which project
│   └── note.py                    ← a single user note attached to a saved paper
│                                     (a saved paper can have any number of notes)
├── templates/                    ← the HTML (Jinja2 templates)
│   ├── base_auth.html             ← shared layout for login/register
│   ├── base_app.html              ← shared layout for logged-in pages (sidebar + content)
│   ├── login.html / register.html
│   ├── dashboard.html
│   ├── projects.html / new_project.html / edit_project.html / project_detail.html
│   ├── choose_project.html        ← pick a project before searching, if you have more than one
│   ├── paper_search.html          ← search form, results, filters, pagination
│   ├── project_papers.html        ← a project's full list of saved papers
│   ├── project_paper_detail.html  ← a saved paper within a project: AI Summary,
│   │                                 Relevance Analysis, and its notes
│   ├── paper_detail.html          ← a paper's own page, independent of any one project
│   ├── my_papers.html             ← every paper saved across all of a user's projects
│   ├── ai_analysis.html           ← the "AI Paper Analysis" hub: every saved paper,
│   │                                 which projects it's in, and its analysis status
│   └── settings.html              ← profile, password change, danger zone (delete account)
├── static/
│   ├── css/style.css              ← the whole design system in one file (Fraunces +
│   │                                 Inter fonts, color palette, cards, panels, the
│   │                                 streaming-output styling)
│   └── js/app.js                  ← password show/hide, confirm-before-delete dialogs,
│                                     auto-dismissing flash messages, and the
│                                     fetch-based streaming client for AI Summary/
│                                     Relevance Analysis
├── database/                     ← researchlens.db (SQLite file), created here on first run
├── uploads/                      ← uploaded PDFs, saved under randomly generated
│                                     filenames so two users' files never collide
├── data/                         ← reserved for future features (e.g. cached embeddings)
├── requirements.txt
├── .env.example                  ← copy to .env and fill in your keys (section 5)
└── .gitignore
```

**How a page request flows:** browser hits a URL → Flask matches it to a function in
`routes/` → that function talks to `services/` to read/write the database → it picks a
template from `templates/` and fills in the blanks → Flask sends back the finished HTML.
The AI Summary and Relevance Analysis endpoints work a little differently: the browser
opens a streaming `fetch()` request, and `openai_service.py` streams tokens back from
OpenAI's Responses API through the Flask route to the page in real time, the same way
ChatGPT's own answers appear word by word, rather than making the user wait for the
whole result before showing anything.

**On login sessions:** Flask keeps track of who's logged in using a signed cookie
(`session["user_id"]`). The `login_required` decorator (defined in `main_routes.py`
and reused by every blueprint) checks for that cookie before running a page's code, and
sends visitors to `/login` if it's missing.

**A note on access control:** every query for a specific project or paper filters by
the *requesting user's own id*, not just the record's id (see `get_project_for_user`
and `user_can_access_paper`) - this is what stops one account from viewing or guessing
into another account's data.

---

## 8. Feature tour by sprint

### Sprint 1 - Foundation & Authentication
- Secure registration, login, and logout, with passwords hashed and salted via bcrypt
  (never stored in plain text).
- Session-based authentication guarding every workspace page.
- A dashboard with stat cards and a "recently viewed" projects list.
- Research-project management: create and view.
- A Settings page for updating display name and password, both re-checked against the
  current password before saving.
- Full account deletion (password-confirmed, cascading to the account's own projects
  and saved papers).

### Sprint 2 - Academic Research Discovery
- Combined paper search across **Semantic Scholar** and **OpenAlex**, two free,
  official scholarly APIs, merged and de-duplicated by DOI (falling back to title) so
  the same paper never appears twice.
- Year-range filtering and sort-by (relevance / newest / oldest), with server-side
  pagination.
- Full project CRUD (create, edit, delete) and a save/remove workflow linking papers
  to a project's library.
- Direct PDF upload with text extraction via PyMuPDF.
- The complete custom Flask + Jinja2 + hand-written CSS interface (Fraunces for
  headings, Inter for body text) that this build has used since before Sprint 1's
  submission, replacing the originally planned Streamlit frontend.

### Sprint 3 - AI Paper Analysis
- **OpenAI-powered AI Summary:** a structured, 300-500 word summary generated for any
  saved paper, streamed live into the page as it's written rather than appearing all
  at once after a wait.
- **Relevance Analysis:** an AI-generated assessment of how relevant a saved paper is
  to a project's specific research question, also streamed live.
- **Per-paper detail page** (`project_paper_detail.html`): one place to read a saved
  paper's abstract, generate or re-read its AI Summary and Relevance Analysis, and
  manage its notes, scoped to the project it's saved in.
- **"AI Paper Analysis" hub page** (`/analysis`): every paper saved across all of a
  user's projects in one view, showing which projects each paper belongs to and
  whether it's been analyzed yet.
- **Multi-note system:** any number of free-text notes per saved paper (not just one),
  each with an optional custom title, addable/editable/deletable independently.

---

## 9. What's next

Two sprints remain on the project roadmap:

- **Sprint 4 - Research Intelligence (Agentic RAG):** evidence tracking that links AI
  output back to the specific saved paper(s) it drew from, "Ask Your Literature"
  (question-answering grounded in and cited to a user's own saved papers), structured
  paper comparison, and a minimal tool-using OpenAI Agent as the project's core
  agentic-AI deliverable.
- **Sprint 5 - Integration, Testing & Final Prototype:** a prepared offline-safe demo
  mode, usability and AI-accuracy testing, end-to-end testing of authentication and
  search, and bug fixes.

These are also visible in the app itself: the sidebar (`base_app.html`) marks the
Literature Matrix, Ask Your Literature, and Research Gaps sections "Soon" until their
sprints land.
