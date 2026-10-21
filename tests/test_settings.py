# tests/test_settings.py
#
# Settings page: changing your display name and your password. This file was added to
# cover a real bug a teammate found by hand (see docs/Final_Manual_Testing_Checklist.md,
# row L2/L3): the "Change password" form accepted a "new" password that was actually
# identical to your current one, silently "succeeding" without changing anything -
# fixed in routes/settings_routes.py's update_password() by checking the new password
# against the real stored hash, not just running it through the normal strength rules.

from tests._dbtest import DatabaseTestCase, register


class UpdatePasswordTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        register(self.client, email="settingsuser@example.com", password="GoodPass1!")

    def _submit(self, current_password, new_password, confirm_new_password=None):
        return self.client.post(
            "/settings/password",
            data={
                "current_password": current_password,
                "new_password": new_password,
                "confirm_new_password": confirm_new_password if confirm_new_password is not None else new_password,
            },
        )

    def test_changing_to_a_genuinely_new_password_succeeds(self):
        response = self._submit("GoodPass1!", "BrandNewPass2!", "BrandNewPass2!")
        self.assertEqual(response.status_code, 302)  # redirected back to /settings on success

        # The new password should actually work on the next login.
        self.client.post("/logout")
        login = self.client.post(
            "/login", data={"email": "settingsuser@example.com", "password": "BrandNewPass2!"},
            follow_redirects=True,
        )
        self.assertIn(b"Dashboard", login.data)

    def test_new_password_identical_to_current_password_is_rejected(self):
        # The exact bug: submitting the SAME password as both "current" and "new"
        # used to pass every check (it's a valid password, and it "matches" itself in
        # confirm_new_password) and silently succeed, instead of asking for a password
        # that's actually different.
        response = self._submit("GoodPass1!", "GoodPass1!", "GoodPass1!")
        self.assertIn(b"must be different from your current password", response.data)

        # And the stored password must be untouched - logging in with it still works,
        # and nothing about this "rejected" request quietly changed anything.
        self.client.post("/logout")
        login = self.client.post(
            "/login", data={"email": "settingsuser@example.com", "password": "GoodPass1!"},
            follow_redirects=True,
        )
        self.assertIn(b"Dashboard", login.data)

    def test_wrong_current_password_is_still_rejected(self):
        response = self._submit("TotallyWrongPass1!", "BrandNewPass2!", "BrandNewPass2!")
        self.assertIn(b"not your current password", response.data)
