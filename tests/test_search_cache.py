# tests/test_search_cache.py
#
# Regression tests for two rounds of the same real bug, found by hand on the live app:
#
# Round 1: "I noticed the search works but after the search, when I try to save a
# paper to a project or go to the next page and it reloads, it shows [the
# rate-limited] error sometimes." Even with a personal SEMANTIC_SCHOLAR_API_KEY
# configured, the guaranteed rate is only 1 request/second, shared by the whole app -
# and both "save a paper" (which redirects straight back to /search) and "next page"
# land on the same GET /search route with the same query, which used to mean a
# brand-new, fully redundant live Semantic Scholar + OpenAlex call every single time.
#
# Round 2: the first fix cached results per (user, project, query) - which missed the
# case of searching the SAME text in a DIFFERENT project a few seconds later: "This
# time I typed an input for the search of a paper in project and it worked normally,
# then I went to search for paper in another project using the same input I used in
# the other project and I got this error." That's a different cache key under the old
# scheme, so it still refetched live and could still trip the shared rate limit - even
# though it was, for the API's purposes, the exact same search.
#
# The real fix: routes/papers_routes.py's _search_academic_sources_cached() caches by
# the normalised query text ALONE - not who's searching or which project - since the
# search results don't depend on either, and the thing being protected (Semantic
# Scholar's shared 1-request/second limit) doesn't care who's asking either. These
# tests cover that caching behaviour directly - no network call, no live API -
# consistent with test_search_dedup.py's approach to this same route module.

import time

from tests._dbtest import DatabaseTestCase
import routes.papers_routes as papers_routes


class SearchResultsCacheTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        # Every test starts from a clean cache - otherwise an earlier test's cached
        # entry could make a later test look like it "didn't re-fetch" for the wrong
        # reason.
        papers_routes._search_results_cache.clear()

        self.call_count = 0

        def fake_search_academic_sources(query):
            self.call_count += 1
            return ([{"title": f"Result for {query}", "doi": None}], ["Semantic Scholar", "OpenAlex"], None)

        # Swap out the real, network-hitting function for the duration of each test,
        # and put the real one back afterwards no matter what.
        self._real_search_academic_sources = papers_routes._search_academic_sources
        papers_routes._search_academic_sources = fake_search_academic_sources

    def tearDown(self):
        papers_routes._search_academic_sources = self._real_search_academic_sources
        papers_routes._search_results_cache.clear()
        super().tearDown()

    def test_repeat_search_within_ttl_reuses_cached_results_instead_of_refetching(self):
        # This is exactly "search, then save a paper (redirect back to the same
        # search), or click next page" - the second call must not hit the live APIs.
        papers_routes._search_academic_sources_cached("ai in education")
        papers_routes._search_academic_sources_cached("ai in education")

        self.assertEqual(self.call_count, 1)

    def test_a_different_query_still_fetches_live(self):
        papers_routes._search_academic_sources_cached("ai in education")
        papers_routes._search_academic_sources_cached("something else entirely")

        self.assertEqual(self.call_count, 2)

    def test_the_same_query_in_a_different_project_reuses_the_cache(self):
        # The exact bug report: search "machine learning" in one project, then search
        # the same text again from a different project a moment later - it's the same
        # live question to Semantic Scholar/OpenAlex either way, so the second call
        # must NOT hit the live APIs again. (project_id isn't even a parameter here
        # any more - this just simulates what happens when search() is called from two
        # different projects with the same query text.)
        papers_routes._search_academic_sources_cached("machine learning")
        papers_routes._search_academic_sources_cached("machine learning")

        self.assertEqual(self.call_count, 1)

    def test_query_matching_ignores_case_and_surrounding_whitespace(self):
        # "Machine Learning" and "  machine learning " are the same search as far as
        # this cache (and the rate limit it's protecting) are concerned.
        papers_routes._search_academic_sources_cached("Machine Learning")
        papers_routes._search_academic_sources_cached("  machine learning  ")

        self.assertEqual(self.call_count, 1)

    def test_an_expired_cache_entry_is_fetched_live_again(self):
        papers_routes._search_academic_sources_cached("ai in education")

        # Simulate the cache entry having aged past its TTL, rather than actually
        # sleeping SEARCH_CACHE_TTL_SECONDS in a test.
        cache_key = papers_routes._normalize_search_cache_key("ai in education")
        papers_routes._search_results_cache[cache_key]["expires_at"] = time.time() - 1

        papers_routes._search_academic_sources_cached("ai in education")

        self.assertEqual(self.call_count, 2)

    def test_cached_results_returned_match_what_was_actually_fetched(self):
        results, sources_used, search_error = papers_routes._search_academic_sources_cached("ai in education")
        cached_results, cached_sources_used, cached_search_error = papers_routes._search_academic_sources_cached(
            "ai in education",
        )

        self.assertEqual(results, cached_results)
        self.assertEqual(sources_used, cached_sources_used)
        self.assertEqual(search_error, cached_search_error)
        self.assertEqual(results[0]["title"], "Result for ai in education")
