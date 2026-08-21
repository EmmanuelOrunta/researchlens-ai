# ResearchLens AI (Flask + HTML/CSS/JS build)

An AI-assisted academic research workspace. This is the **Sprint 1** build: user
registration, login, logout, a dashboard, and basic research-project creation - the
foundation everything else (paper search, AI analysis, RAG Q&A, research-gap detection)
will be built on top of in later sprints.

This build replaces the earlier Streamlit prototype with a real HTML/CSS/JS frontend
served by a Flask backend, for full control over the look and feel. The database logic
(SQLite + SQLAlchemy) carried over unchanged - it never depended on Streamlit in the
first place.

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

---

## 5. Run the app

```
python app.py
```

You'll see output ending in something like `Running on http://127.0.0.1:5000`. Open
that address in your browser - you should see the ResearchLens AI login screen.

Try it out:
1. Click **Create one** (register), fill in the form, submit.
2. You'll land on the Dashboard, signed in.
3. Click **+ New Research Project**, create one, see it appear on your dashboard.
4. Click **Sign out**, then log back in with the same email/password.

To stop the app: click the terminal and press `Ctrl+C`.

---

## 6. How the code is organised

```
researchlens-ai-flask/
├── app.py                     ← entry point: run this file. Creates the Flask app.
├── routes/
│   ├── auth_routes.py         ← /login, /register, /logout
│   └── main_routes.py         ← /  (dashboard), /projects/new
├── services/                  ← the actual logic, kept separate from the routes/templates
│   ├── database_service.py    ← database connection + table creation
│   ├── auth_service.py        ← password hashing, user lookup/creation
│   └── project_service.py     ← create/list research projects
├── models/                    ← one file per database table
│   ├── user.py
│   └── project.py
├── templates/                 ← the actual HTML (Jinja2 templates)
│   ├── base_auth.html         ← shared layout for login/register (centered card, no sidebar)
│   ├── base_app.html          ← shared layout for logged-in pages (sidebar + content)
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html
│   └── new_project.html
├── static/
│   ├── css/style.css          ← all the styling - one file, driven by CSS variables at the top
│   └── js/app.js              ← password show/hide toggle, auto-dismissing flash messages
├── database/                  ← researchlens.db (SQLite file) created here on first run
├── data/                      ← reserved for the demo dataset (Sprint 2+)
├── uploads/                   ← reserved for user-uploaded PDFs (Sprint 3+)
├── requirements.txt
├── .env.example                ← copy to .env when you're ready to add API keys
└── .gitignore
```

**How a page request flows:** browser hits a URL → Flask matches it to a function in
`routes/` → that function talks to `services/` to read/write the database → it picks a
template from `templates/` and fills in the blanks → Flask sends back the finished HTML.
`static/css/style.css` and `static/js/app.js` are just plain files the browser downloads
alongside the HTML, same as any website.

**On login sessions:** Flask keeps track of who's logged in using a signed cookie
(`session["user_id"]`). The `login_required` decorator at the top of `main_routes.py`
checks for that cookie before running a page's code, and sends visitors to `/login` if
it's missing.

---

## 7. About the API keys (for later sprints)

Sprint 1 doesn't call any external APIs. Two services come into play starting Sprint 2/3:

- **Semantic Scholar / OpenAlex** - free academic search APIs.
- **OpenAI API** - used later for AI paper summaries, "Ask Your Literature," and
  research-gap detection. Requires an account and billing at
  [platform.openai.com](https://platform.openai.com/); usage is billed per request.

When ready, copy `.env.example` to `.env` and fill in your keys. `.env` is already
excluded from Git.

---

## 8. What's next

This covers Sprint 1 from the project plan. Coming in later sprints, in order:
academic paper search (Semantic Scholar/OpenAlex), saving papers to a project,
AI-generated paper analysis, the literature comparison matrix, paper comparison,
"Ask Your Literature" (RAG), and potential research-gap detection - all served through
these same Flask routes and templates, so the AI features will live in the same app
rather than a second, separate tool.
