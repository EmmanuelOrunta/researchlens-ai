# tests/test_search_already_saved.py
#
# Covers the "SAVED TO PROJECT" indicator added to paper_search.html: a search result
# that's already in the current project's library should show a clear badge next to
# it, not look exactly like a paper you haven't saved yet. The route
# (routes/papers_routes.py's search()) marks each result with already_saved_to_project
# by matching it against the project's saved papers using the same DOI/normalised-
# title key _dedupe_key already uses to spot the same paper from two different
# sources - these tests exercise that matching through the real route, with the live
# Semantic Scholar/OpenAlex call swapped out for a fixed fake result set (same
# approach as test_search_cache.py) so nothing here depends on a network call.

from tests._dbtest import DatabaseTestCase, register
from services.database_service import get_session
from services.auth_service import get_user_by_email
from services.project_service import create_project
from services.paper_service import create_paper_from_search_result, save_paper_to_project
import routes.papers_routes as papers_routes


class AlreadySavedIndicatorTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        papers_routes._search_results_cache.clear()

        register(self.client, email="librarian@example.com", password="GoodPass1!")

        db = get_session()
        try:
            user = get_user_by_email(db, "librarian@example.com")
            self.project = create_project(
                db, user.id, title="Generative AI in Higher Education",
                research_question="How is GenAI used in HE?", research_field="Education", keywords="AI, HE",
            )
            # Already saved to this project, via a DOI that matches one of the two
            # fake search results below - this is the one that should get the badge.
            saved_paper = create_paper_from_search_result(db, {
                "title": "A Paper We Already Saved", "doi": "10.1000/already-saved",
                "source": "semantic_scholar",
            })
            save_paper_to_project(db, self.project.id, saved_paper.id)
        finally:
            db.close()

        def fake_search_academic_sources(query):
            return (
                [
                    # Same DOI as the paper saved above - different title casing/source,
                    # on purpose, to prove this matches on DOI rather than an exact
                    # external_id or title string.
                    {"title": "A Paper We Already Saved (preprint)", "doi": "10.1000/ALREADY-SAVED",
                     "authors": "A. Author", "year": 2024, "abstract": "...", "source": "openalex",
                     "external_id": "oa-999", "url": None, "open_access_pdf_url": None},
                    {"title": "A Totally New Paper", "doi": "10.1000/brand-new",
                     "authors": "B. Author", "year": 2025, "abstract": "...", "source": "semantic_scholar",
                     "external_id": "ss-111", "url": None, "open_access_pdf_url": None},
                ],
                ["Semantic Scholar", "OpenAlex"],
                None,
            )

        self._real_search_academic_sources = papers_routes._search_academic_sources
        papers_routes._search_academic_sources = fake_search_academic_sources

    def tearDown(self):
        papers_routes._search_academic_sources = self._real_search_academic_sources
        papers_routes._search_results_cache.clear()
        super().tearDown()

    def test_a_paper_already_saved_to_this_project_is_marked_saved(self):
        response = self.client.get(f"/projects/{self.project.id}/search?query=ai+in+education")
        self.assertIn(b"Saved to Generative AI in Higher Education", response.data)

    def test_a_paper_not_yet_saved_is_not_marked_saved(self):
        response = self.client.get(f"/projects/{self.project.id}/search?query=ai+in+education")
        page = response.data.decode()
        # The badge text should appear exactly once - for the already-saved paper -
        # not next to "A Totally New Paper" as well.
        self.assertEqual(page.count("Saved to Generative AI in Higher Education"), 1)
        self.assertIn("A Totally New Paper", page)

    def test_a_second_project_without_this_paper_does_not_show_it_as_saved(self):
        db = get_session()
        try:
            user = get_user_by_email(db, "librarian@example.com")
            other_project = create_project(
                db, user.id, title="A Completely Different Project",
                research_question="Something else", research_field="Other", keywords="",
            )
        finally:
            db.close()

        response = self.client.get(f"/projects/{other_project.id}/search?query=ai+in+education")
        self.assertNotIn(b"badge-saved", response.data)
