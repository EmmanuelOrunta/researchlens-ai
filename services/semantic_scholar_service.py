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


def search_papers(query: str, limit: int = 10):
    """
    Search Semantic Scholar for papers matching `query`.

    Returns a list of result dicts on success (the list is empty if the search simply
    found nothing). Returns None if the request failed outright (no internet, Semantic
    Scholar is down, rate-limited, etc.) - the route checks for that None specifically
    so it can show "couldn't reach Semantic Scholar" instead of a confusing empty list.
    """
    headers = {"User-Agent": "ResearchLensAI-StudentProject (mailto:example@example.com)"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    try:
        response = requests.get(
            SEARCH_URL,
            params={"query": query, "limit": limit, "fields": FIELDS},
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        # Printing here means the REAL reason (timeout, 429 rate limit, DNS failure,
        # etc.) shows up in your terminal where `python app.py` is running, instead of
        # disappearing silently - worth checking there if search keeps failing.
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