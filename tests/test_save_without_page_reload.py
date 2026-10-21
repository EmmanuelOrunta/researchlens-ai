# tests/test_save_without_page_reload.py
#
# A teammate noticed that clicking "Save to Project" on the search results page took
# them back to the TOP of the page, losing their place in a long results list (fixed
# alongside the "already saved" badge from the same feedback round - see
# tests/test_search_already_saved.py). The fix: paper_search.html's save form is now
# submitted via fetch() (see [data-save-to-project-form] in app.js) instead of a plain
# HTML form POST, so the page never navigates at all.
#
# That only works because routes/papers_routes.py's save_from_search() now answers
# differently depending on how it was asked: a JS fetch() call (marked with an
# X-Requested-With: XMLHttpRequest header) gets back a small JSON acknowledgement to
# react to in place, while anything else - a browser with JS disabled, or any other
# caller - still gets the original redirect-back-to-search-with-a-flash-message
# behaviour, unchanged. These tests cover both paths actually saving the paper, and
# each one answering the way its caller expects.

from tests._dbtest import DatabaseTestCase, register
from services.database_service import get_session
from services.auth_service import get_user_by_email
from services.project_service import create_project
from services.paper_service import get_saved_papers_for_project


class SaveWithoutPageReloadTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        register(self.client, email="librarian@example.com", password="GoodPass1!")

        db = get_session()
        try:
            user = get_user_by_email(db, "librarian@example.com")
            self.project = create_project(
                db, user.id, title="Generative AI in Higher Education",
                research_question="How is GenAI used in HE?", research_field="Education", keywords="AI, HE",
            )
        finally:
            db.close()

    def _save_paper_form_data(self, title="A Paper From Search", external_id="ss-123", doi="10.1000/xyz"):
        return {
            "external_id": external_id, "title": title, "authors": "Some Author", "year": "2024",
            "abstract": "An abstract.", "doi": doi, "url": "", "source": "semantic_scholar",
            "open_access_pdf_url": "", "query": "ai in education", "year_from": "", "year_to": "",
            "sort": "relevance", "page": "1",
        }

    def test_a_fetch_request_gets_json_back_and_does_not_redirect(self):
        response = self.client.post(
            f"/projects/{self.project.id}/papers/save",
            data=self._save_paper_form_data(),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, "application/json")
        body = response.get_json()
        self.assertEqual(body["success"], True)
        self.assertEqual(body["project_title"], "Generative AI in Higher Education")

    def test_a_fetch_request_still_actually_saves_the_paper(self):
        self.client.post(
            f"/projects/{self.project.id}/papers/save",
            data=self._save_paper_form_data(title="Saved Via Fetch"),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        db = get_session()
        try:
            titles = {paper.title for paper in get_saved_papers_for_project(db, self.project.id)}
        finally:
            db.close()
        self.assertIn("Saved Via Fetch", titles)

    def test_a_plain_form_submit_without_js_still_redirects_with_a_flash_message(self):
        # No X-Requested-With header here - this is what a browser with JS disabled
        # (or any other non-fetch caller) actually sends, and it must keep working
        # exactly as it did before this change.
        response = self.client.post(
            f"/projects/{self.project.id}/papers/save",
            data=self._save_paper_form_data(title="Saved The Old-Fashioned Way"),
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Paper saved to your project.", response.data)

        db = get_session()
        try:
            titles = {paper.title for paper in get_saved_papers_for_project(db, self.project.id)}
        finally:
            db.close()
        self.assertIn("Saved The Old-Fashioned Way", titles)
