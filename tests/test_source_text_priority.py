# tests/test_source_text_priority.py
#
# The user noticed every AI feature (AI Summary, Relevance Analysis, Literature
# Matrix) always seemed to work from a paper's abstract, and asked whether it ever
# reads the full paper instead - it has always been technically ABLE to (Semantic
# Scholar/OpenAlex often point at a free, open-access PDF, and
# pdf_service.fetch_and_extract_text_from_url() already knew how to download and read
# one), but services/paper_service.py's get_or_fetch_source_text() checked
# paper.abstract FIRST, so that full-text path could never actually run on a search
# result that also had an abstract - which is nearly every one of them.
#
# The fix reorders that priority: prefer a paper's full text (already-stored, or
# freshly downloaded from its open-access link) whenever one is genuinely available,
# and fall back to the abstract only when it isn't. These tests cover that ordering
# directly, with fetch_and_extract_text_from_url() swapped out for a fake (no real
# network call, no real PDF) - consistent with how test_search_cache.py and
# test_search_already_saved.py fake out their own network-touching dependencies.

from tests._dbtest import DatabaseTestCase
from services.database_service import get_session
from services.paper_service import create_paper_from_search_result, get_or_fetch_source_text
import services.paper_service as paper_service


class SourceTextPriorityTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.db = get_session()
        self._real_fetch = paper_service.fetch_and_extract_text_from_url

    def tearDown(self):
        paper_service.fetch_and_extract_text_from_url = self._real_fetch
        self.db.close()
        super().tearDown()

    def _fake_fetch_returning(self, text=None, error=None):
        def fake(url):
            return text, error
        paper_service.fetch_and_extract_text_from_url = fake

    def test_already_extracted_text_is_used_without_fetching_again(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": "A short abstract.",
            "open_access_pdf_url": "https://example.com/paper.pdf",
            "source": "semantic_scholar",
        })
        paper.extracted_text = "The full cached body text of the paper."
        self.db.commit()

        def fetch_should_not_be_called(url):
            raise AssertionError("Shouldn't re-fetch when extracted_text is already stored")
        paper_service.fetch_and_extract_text_from_url = fetch_should_not_be_called

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(error)
        self.assertEqual(text, "The full cached body text of the paper.")

    def test_full_paper_is_preferred_over_the_abstract_when_both_are_available(self):
        # This is the exact behaviour the user flagged: a paper that has BOTH an
        # abstract AND a free open-access copy should actually read the full paper,
        # not just the one-paragraph abstract.
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": "Just the abstract paragraph.",
            "open_access_pdf_url": "https://example.com/paper.pdf",
            "source": "semantic_scholar",
        })
        self._fake_fetch_returning(text="Full body text: intro, methods, results, discussion.")

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(error)
        self.assertEqual(text, "Full body text: intro, methods, results, discussion.")
        self.assertNotEqual(text, paper.abstract)

    def test_fetched_full_text_is_cached_onto_the_paper_for_next_time(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": "An abstract.",
            "open_access_pdf_url": "https://example.com/paper.pdf",
            "source": "semantic_scholar",
        })
        self._fake_fetch_returning(text="Downloaded full text.")

        get_or_fetch_source_text(self.db, paper)

        refetched = self.db.query(type(paper)).get(paper.id)
        self.assertEqual(refetched.extracted_text, "Downloaded full text.")

    def test_falls_back_to_the_abstract_if_the_open_access_fetch_fails(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": "The abstract still works as a fallback.",
            "open_access_pdf_url": "https://example.com/paper.pdf",
            "source": "semantic_scholar",
        })
        self._fake_fetch_returning(error="Couldn't download the open-access PDF for this paper.")

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(error)
        self.assertEqual(text, "The abstract still works as a fallback.")

    def test_reports_the_fetch_error_when_there_is_no_abstract_to_fall_back_to(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": None,
            "open_access_pdf_url": "https://example.com/paper.pdf",
            "source": "semantic_scholar",
        })
        self._fake_fetch_returning(error="The open-access PDF didn't contain any extractable text.")

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(text)
        self.assertEqual(error, "The open-access PDF didn't contain any extractable text.")

    def test_uses_the_abstract_when_there_is_no_open_access_link_at_all(self):
        # Unchanged baseline behaviour: a paywalled paper with no open-access copy
        # still falls back to its abstract, exactly as before this change.
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": "The only text available for this paper.",
            "open_access_pdf_url": None, "source": "semantic_scholar",
        })

        def fetch_should_not_be_called(url):
            raise AssertionError("Shouldn't attempt a fetch with no open_access_pdf_url")
        paper_service.fetch_and_extract_text_from_url = fetch_should_not_be_called

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(error)
        self.assertEqual(text, "The only text available for this paper.")

    def test_a_paper_with_nothing_available_reports_a_clear_error(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "A Paper", "abstract": None, "open_access_pdf_url": None,
            "source": "semantic_scholar",
        })

        text, error = get_or_fetch_source_text(self.db, paper)
        self.assertIsNone(text)
        self.assertIn("no abstract", error)
