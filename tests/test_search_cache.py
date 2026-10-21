# tests/test_search_cache.py
#
# Regression test for a real bug a teammate found by hand: "I noticed the search
# works but after the search, when I try to save a paper to a project or go to the
# next page and it reloads, it shows [the rate-limited] error sometimes." Even with a
# personal SEMANTIC_SCHOLAR_API_KEY configured, the guaranteed rate is only 1
# request/second, shared by the whole app - and both "save a paper" (which redirects
# straight back to /search) and "next page" land on the same GET /search route with
# the same query, which used to mean a brand-new, fully redundant live Semantic
# Scholar + OpenAlex call every single time.
#
# The fix: routes/papers_routes.py's _search_academic_sources_cached() reuses the raw
# merged results for a repeat of the exact same (user, project, query) within
# SEARCH_CACHE_TTL_SECONDS, instead of calling the live APIs again. These tests cover
# that caching behaviour directly - no network call, no live API - consistent with
# test_search_dedup.py's approach to this same route module.

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
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="ai in education")
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="ai in education")

        self.assertEqual(self.call_count, 1)

    def test_a_different_query_still_fetches_live(self):
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="ai in education")
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="something else entirely")

        self.assertEqual(self.call_count, 2)

    def test_the_same_query_for_a_different_project_still_fetches_live(self):
        # Project A and project B both searching "machine learning" shouldn't share a
        # cache entry - each project's search is its own.
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="machine learning")
        papers_routes._search_academic_sources_cached(user_id=1, project_id=2, query="machine learning")

        self.assertEqual(self.call_count, 2)

    def test_the_same_query_for_a_different_user_still_fetches_live(self):
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="machine learning")
        papers_routes._search_academic_sources_cached(user_id=2, project_id=1, query="machine learning")

        self.assertEqual(self.call_count, 2)

    def test_an_expired_cache_entry_is_fetched_live_again(self):
        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="ai in education")

        # Simulate the cache entry having aged past its TTL, rather than actually
        # sleeping SEARCH_CACHE_TTL_SECONDS in a test.
        cache_key = (1, 1, "ai in education")
        papers_routes._search_results_cache[cache_key]["expires_at"] = time.time() - 1

        papers_routes._search_academic_sources_cached(user_id=1, project_id=1, query="ai in education")

        self.assertEqual(self.call_count, 2)

    def test_cached_results_returned_match_what_was_actually_fetched(self):
        results, sources_used, search_error = papers_routes._search_academic_sources_cached(
            user_id=1, project_id=1, query="ai in education",
        )
        cached_results, cached_sources_used, cached_search_error = papers_routes._search_academic_sources_cached(
            user_id=1, project_id=1, query="ai in education",
        )

        self.assertEqual(results, cached_results)
        self.assertEqual(sources_used, cached_sources_used)
        self.assertEqual(search_error, cached_search_error)
        self.assertEqual(results[0]["title"], "Result for ai in education")
