# services/openalex_service.py
#
# A second, independent academic search source (from the project plan's "Primary
# Academic Sources" section). No API key needed, no signup - OpenAlex's search API is
# fully open. This exists mainly as a fallback: if Semantic Scholar is unreachable or
# rate-limited, papers_routes.py automatically tries this instead, so a single flaky
# API doesn't take the whole search feature down.
#
# Just like semantic_scholar_service.py, this only returns plain dicts shaped the same
# way - the search results page and paper_service.py don't need to know or care which
# of the two sources a result came from.

import requests

SEARCH_URL = "https://api.openalex.org/works"
REQUEST_TIMEOUT_SECONDS = 10

# OpenAlex's own ceiling on per-page - asking for more just gets clamped/rejected
# server-side. OpenAlex is far more generous than Semantic Scholar here (no per-key
# rate limit for reasonable use), which is part of why it tends to fill in results
# whenever Semantic Scholar's shared unauthenticated pool is rate-limiting this app.
MAX_LIMIT = 200

# OpenAlex asks API users to identify themselves with a contact in the User-Agent -
# it's not required, but being a "good citizen" here makes OpenAlex less likely to
# rate-limit us. Feel free to swap in a real contact email for your team.
HEADERS = {"User-Agent": "ResearchLensAI-StudentProject (mailto:example@example.com)"}


def search_papers(query: str, limit: int = 10):
    """
    Search OpenAlex for works matching `query`. Same return shape as
    semantic_scholar_service.search_papers(): a list of dicts on success (possibly
    empty), or None if the request failed outright.
    """
    try:
        response = requests.get(
            SEARCH_URL,
            params={"search": query, "per-page": min(limit, MAX_LIMIT)},
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        print(f"[openalex_service] search failed: {error}")
        return None

    results = []
    for work in payload.get("results", []):
        authorships = work.get("authorships") or []
        author_names = ", ".join(
            (a.get("author") or {}).get("display_name", "") for a in authorships
        ).strip(", ")

        doi = work.get("doi")
        if doi:
            doi = doi.replace("https://doi.org/", "")

        results.append({
            # OpenAlex IDs look like "https://openalex.org/W2741809807" - still fine
            # as a unique dedupe key even though the format differs from Semantic
            # Scholar's short paperId.
            "external_id": work.get("id"),
            "title": work.get("title") or work.get("display_name") or "Untitled",
            "authors": author_names,
            "year": work.get("publication_year"),
            "abstract": _rebuild_abstract(work.get("abstract_inverted_index")),
            "doi": doi,
            "url": work.get("id"),
        })

    return results


def _rebuild_abstract(inverted_index):
    """
    OpenAlex doesn't store abstracts as plain text - to save space, it stores an
    "inverted index" mapping each word to the list of positions it appears at
    (e.g. {"the": [0, 5], "cat": [1]}). This puts the words back in order.
    """
    if not inverted_index:
        return None

    positions = {}
    for word, word_positions in inverted_index.items():
        for position in word_positions:
            positions[position] = word

    return " ".join(positions[i] for i in sorted(positions))