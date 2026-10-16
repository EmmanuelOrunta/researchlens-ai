# tests/test_auth.py
#
# Sprint 5, roadmap item 4: "Test authentication - verify registration, login, logout
# and account management end-to-end." These tests drive the real Flask routes exactly
# like a browser would (POSTing real form data), against a disposable test database -
# see tests/_dbtest.py.

from tests._dbtest import DatabaseTestCase, register


class RegistrationTests(DatabaseTestCase):

    def test_valid_registration_logs_the_user_in(self):
        response = register(self.client)
        # follow_redirects=True means we land on wherever /register redirects to after
        # success - a logged-in user should end up on the Dashboard, not back on the
        # registration form with error text.
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Dashboard", response.data)

    def test_duplicate_email_is_rejected(self):
        register(self.client, email="dupe@example.com")
        self.client.post("/logout")
        second = register(self.client, name="Someone Else", email="dupe@example.com")
        self.assertIn(b"already exists", second.data)

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            "/register",
            data={"name": "Test User", "email": "weak@example.com",
                  "password": "allsmall1", "confirm_password": "allsmall1"},
        )
        # No uppercase letter - should bounce back to the form with an inline error,
        # not create the account.
        self.assertIn(b"uppercase letter", response.data)

    def test_mismatched_confirm_password_is_rejected(self):
        response = self.client.post(
            "/register",
            data={"name": "Test User", "email": "mismatch@example.com",
                  "password": "GoodPass1!", "confirm_password": "GoodPass1?"},
        )
        self.assertIn(b"do not match", response.data)


class LoginTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        register(self.client, email="loginuser@example.com", password="GoodPass1!")
        self.client.post("/logout")

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

    def test_unknown_email_gives_the_same_generic_error(self):
        # Deliberately the SAME message as a wrong password (see routes/auth_routes.py)
        # - this is what stops a login form from being usable to check which emails
        # have an account ("user enumeration").
        response = self.client.post(
            "/login", data={"email": "nobody@example.com", "password": "Whatever1!"},
        )
        self.assertIn(b"Incorrect email or password", response.data)


class SessionProtectionTests(DatabaseTestCase):

    def test_dashboard_redirects_to_login_when_signed_out(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_logout_clears_the_session(self):
        register(self.client, email="logoutuser@example.com", password="GoodPass1!")
        self.client.post("/logout")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
