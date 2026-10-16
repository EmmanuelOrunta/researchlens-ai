# tests/test_search_dedup.py
#
# Sprint 5, roadmap item 5: "Test academic search - verify Semantic Scholar/OpenAlex
# search, filtering, sorting and pagination." These tests cover the two pure,
# deterministic pieces of that logic directly - no network call, no live API - the
# de-duplication key (routes/papers_routes.py's _dedupe_key) and the year-range filter
# (_filter_by_year). Actually calling the live Semantic Scholar/OpenAlex APIs belongs
# in a manual pass instead (see docs/Sprint5_Plan.md) - an automated test shouldn't
# depend on a third-party service being up, rate-limit-free, and unchanged.

from tests._dbtest import DatabaseTestCase
from routes.papers_routes import _dedupe_key, _filter_by_year


class DedupeKeyTests(DatabaseTestCase):

    def test_same_doi_from_both_sources_produces_the_same_key(self):
        ss_paper = {"doi": "10.1000/ABC123", "title": "A Study of Things"}
        oa_paper = {"doi": "10.1000/abc123", "title": "A completely different title"}
        # Same DOI, different case, different title - still the same paper.
        self.assertEqual(_dedupe_key(ss_paper), _dedupe_key(oa_paper))

    def test_missing_doi_falls_back_to_normalized_title(self):
        paper_a = {"doi": None, "title": "AI in Education: A Review!"}
        paper_b = {"doi": "", "title": "ai in education a review"}
        self.assertEqual(_dedupe_key(paper_a), _dedupe_key(paper_b))

    def test_different_papers_get_different_keys(self):
        paper_a = {"doi": None, "title": "Statistics Education and ChatGPT"}
        paper_b = {"doi": None, "title": "Academic Integrity and LLMs"}
        self.assertNotEqual(_dedupe_key(paper_a), _dedupe_key(paper_b))


class YearFilterTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.results = [
            {"title": "Old paper", "year": 2010},
            {"title": "Mid paper", "year": 2023},
            {"title": "New paper", "year": 2026},
            {"title": "Unknown year paper", "year": None},
        ]

    def test_no_filter_returns_everything_unchanged(self):
        filtered = _filter_by_year(self.results, None, None)
        self.assertEqual(len(filtered), 4)

    def test_lower_bound_excludes_older_papers(self):
        filtered = _filter_by_year(self.results, 2020, None)
        titles = {paper["title"] for paper in filtered}
        self.assertEqual(titles, {"Mid paper", "New paper"})

    def test_upper_bound_excludes_newer_papers(self):
        filtered = _filter_by_year(self.results, None, 2023)
        titles = {paper["title"] for paper in filtered}
        self.assertEqual(titles, {"Old paper", "Mid paper"})

    def test_unknown_year_is_excluded_once_any_filter_is_active(self):
        filtered = _filter_by_year(self.results, 2000, 2030)
        titles = {paper["title"] for paper in filtered}
        self.assertNotIn("Unknown year paper", titles)
