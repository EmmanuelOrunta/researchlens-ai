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
#
# The badge <span> is rendered for EVERY result, not just already-saved ones (plain
# `hidden` on it otherwise) - that's deliberate, so the [data-save-to-project-form]
# handler in app.js can reveal an already-correct badge the instant a save succeeds,
# with no page reload (see tests/test_save_without_page_reload.py). So "is this paper
# marked saved" has to be read as "is ITS badge missing `hidden`", not just "does the
# word 'Saved' appear anywhere in the page" - _badge_tags() below pulls out just the
# opening <span class="badge-saved" ...> tags, in the same order as the results, so
# each one can be checked on its own.

import re

from tests._dbtest import DatabaseTestCase, register
from services.database_service import get_session
from services.auth_service import get_user_by_email
from services.project_service import create_project
from services.paper_service import create_paper_from_search_result, save_paper_to_project
import routes.papers_routes as papers_routes


def _badge_tags(html):
    """Every <span class="badge-saved" ...> opening tag, in document order - one per
    search result card. Check `"hidden" in tag` on each to see if that particular
    result's badge is actually showing."""
    return re.findall(r'<span class="badge-saved"[^>]*>', html)


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

    def test_a_paper_already_saved_to_this_project_has_a_visible_badge(self):
        response = self.client.get(f"/projects/{self.project.id}/search?query=ai+in+education")
        page = response.data.decode()
        self.assertIn("Saved to Generative AI in Higher Education", page)

        badges = _badge_tags(page)
        self.assertEqual(len(badges), 2)  # one per result card, saved or not
        # The first result is the one that matches an already-saved paper (same DOI,
        # different casing/title/source - see fake_search_academic_sources above).
        self.assertNotIn("hidden", badges[0])

    def test_a_paper_not_yet_saved_has_its_badge_hidden(self):
        response = self.client.get(f"/projects/{self.project.id}/search?query=ai+in+education")
        page = response.data.decode()
        self.assertIn("A Totally New Paper", page)

        badges = _badge_tags(page)
        self.assertEqual(len(badges), 2)
        # The second result is "A Totally New Paper" - never saved anywhere, so its
        # badge stays hidden until (if ever) it's saved via the page's own JS.
        self.assertIn("hidden", badges[1])

    def test_a_second_project_without_this_paper_shows_no_visible_badge(self):
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
        page = response.data.decode()

        badges = _badge_tags(page)
        self.assertEqual(len(badges), 2)
        self.assertTrue(all("hidden" in badge for badge in badges))
