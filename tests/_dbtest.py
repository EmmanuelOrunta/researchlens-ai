# tests/_dbtest.py
#
# Shared setup for every test module in this folder. Not itself a test file (its name
# doesn't start with "test_", so `python -m unittest discover` skips it) - it's
# imported BY the real test files instead.
#
# The one thing every test here needs: a real, working copy of this app's database
# that is completely disposable - never the real database/researchlens.db a developer
# might have actual projects saved in. We get that by pointing the RESEARCHLENS_DB_PATH
# environment variable (see services/database_service.py) at a brand-new temp file
# BEFORE this app's modules are imported for the first time, then creating every table
# fresh inside it. DatabaseTestCase.setUp()/tearDown() then wipes and recreates those
# tables before each individual test, so tests never see leftover data from one another
# and can run in any order.

import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(prefix="researchlens_test_", suffix=".db")
os.close(_TEST_DB_FD)
os.environ["RESEARCHLENS_DB_PATH"] = _TEST_DB_PATH
# A real Flask SECRET_KEY isn't needed for tests (nothing here cares if sessions
# survive a server restart), but Flask will refuse to sign the session cookie at all
# without SOME key present - this just needs to be non-empty and stable per test run.
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-secret-key")

from app import app as flask_app  # noqa: E402  (must come after the env vars above)
from services.database_service import Base, engine  # noqa: E402


class DatabaseTestCase(unittest.TestCase):
    """
    Base class for any test that touches the database or goes through Flask routes.
    Subclass this instead of unittest.TestCase directly, and use self.client (a Flask
    test client that keeps the login session cookie between requests, the same way a
    real browser tab would across a login -> dashboard -> logout flow).
    """

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        flask_app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = flask_app.test_client()

    def tearDown(self):
        Base.metadata.drop_all(bind=engine)


def register(client, name="Test User", email="test@example.com", password="GoodPass1!"):
    """Shared helper: POST a valid registration form. Returns the response, already
    redirected-followed so callers can inspect the page it lands on if they want to."""
    return client.post(
        "/register",
        data={"name": name, "email": email, "password": password, "confirm_password": password},
        follow_redirects=True,
    )
