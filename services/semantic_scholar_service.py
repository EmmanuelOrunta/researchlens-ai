# services/semantic_scholar_service.py
#
# Talks to Semantic Scholar's free, public Academic Graph API to search for papers.
# No API key is required for light use (a key just raises the rate limit) - see
# .env.example if you want to add one later via SEMANTIC_SCHOLAR_API_KEY.
#
# This file only ever returns plain Python dicts, never database objects - it doesn't
# know or care about SQLAlchemy. services/paper_service.py is what turns a result dict
# from here into a saved Paper row.

import os
import requests

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,authors,year,abstract,externalIds,url"
REQUEST_TIMEOUT_SECONDS = 10

# The /graph/v1/paper/search endpoint (the "relevance search" endpoint this file calls,
# as opposed to /paper/search/bulk) rejects any limit above 100 - asking for more than
# that just gets you an error response instead of more papers. If you need more than
# 100 results for one query, the real fix is to page through with the `offset` param
# (Semantic Scholar caps limit+offset at 1000 total), not to raise this further.
MAX_LIMIT = 100


def search_papers(query: str, limit: int = 10):
    """
    Search Semantic Scholar for papers matching `query`.

    Returns a list of result dicts on success (the list is empty if the search simply
    found nothing). Returns None if the request failed outright (no internet, Semantic
    Scholar is down, rate-limited, etc.) - the route checks for that None specifically
    so it can show "couldn't reach Semantic Scholar" instead of a confusing empty list.

    Without a personal API key, this request shares one rate-limit pool with every
    other unauthenticated Semantic Scholar user on the internet - so it's normal for
    it to occasionally fail with a 429 (rate limited) even though nothing is wrong with
    this app. A free key (see SEMANTIC_SCHOLAR_API_KEY in .env.example) gives this app
    its own guaranteed 1 request/second instead of competing for that shared pool -
    request one at https://www.semanticscholar.org/product/api#api-key if OpenAlex
    results keep outnumbering Semantic Scholar's.
    """
    headers = {"User-Agent": "ResearchLensAI-StudentProject (mailto:example@example.com)"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    try:
        response = requests.get(
            SEARCH_URL,
            params={"query": query, "limit": min(limit, MAX_LIMIT), "fields": FIELDS},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        # Printing here means the REAL reason (timeout, 429 rate limit, DNS failure,
        # etc.) shows up in your terminal where `python app.py` is running, instead of
        # disappearing silently - worth checking there if search keeps failing. A 429
        # here is the single most common cause and is exactly the "shared pool" issue
        # described above, not a bug.
        print(f"[semantic_scholar_service] search failed: {error}")
        return None

    results = []
    for paper in payload.get("data", []):
        author_names = ", ".join(
            a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")
        )
        external_ids = paper.get("externalIds") or {}

        results.append({
            "external_id": paper.get("paperId"),
            "title": paper.get("title") or "Untitled",
            "authors": author_names,
            "year": paper.get("year"),
            "abstract": paper.get("abstract"),
            "doi": external_ids.get("DOI"),
            "url": paper.get("url"),
        })

    return results