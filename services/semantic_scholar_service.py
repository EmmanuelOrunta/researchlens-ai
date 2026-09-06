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
import time
import requests

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
# openAccessPdf: when Semantic Scholar knows of a free, legal full-text copy of this
# paper (not every paper has one - most paywalled journal articles won't), it comes
# back here as {"url": "...", "status": "..."}. Used as a last-resort fallback for
# papers with no abstract - see paper_service.py's get_or_fetch_source_text().
FIELDS = "title,authors,year,abstract,externalIds,url,openAccessPdf"
REQUEST_TIMEOUT_SECONDS = 10

# The /graph/v1/paper/search endpoint (the "relevance search" endpoint this file calls,
# as opposed to /paper/search/bulk) rejects any limit above 100 - asking for more than
# that just gets you an error response instead of more papers. If you need more than
# 100 results for one query, the real fix is to page through with the `offset` param
# (Semantic Scholar caps limit+offset at 1000 total), not to raise this further.
MAX_LIMIT = 100

# A 429 (rate limited) from Semantic Scholar's shared, unauthenticated pool is often
# gone a second later - one other request just happened to land in the same second.
# Rather than surfacing that as a hard failure straight away, this retries a couple of
# times with a short backoff first, which quietly recovers from most of the
# intermittent "Semantic Scholar didn't respond" errors users otherwise see even
# though nothing is actually wrong. MAX_ATTEMPTS = 3 means: 1 initial try + 2 retries.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0   # attempt 1 waits ~1s, attempt 2 waits ~2s, before trying again
MAX_RETRY_WAIT_SECONDS = 5.0  # cap in case Semantic Scholar's own Retry-After is generous


def _seconds_to_wait(attempt_index: int, retry_after_header) -> float:
    """
    How long to sleep before the next attempt. Semantic Scholar's own `Retry-After`
    response header (when present) is a more accurate signal than a guess, so it's
    preferred - capped so one unusually large value can't stall the search for the
    person waiting on results. Otherwise falls back to a short exponential backoff.
    """
    if retry_after_header:
        try:
            return min(float(retry_after_header), MAX_RETRY_WAIT_SECONDS)
        except ValueError:
            pass
    return min(RETRY_BACKOFF_SECONDS * (attempt_index + 1), MAX_RETRY_WAIT_SECONDS)


def search_papers(query: str, limit: int = 10):
    """
    Search Semantic Scholar for papers matching `query`.

    Returns a list of result dicts on success (the list is empty if the search simply
    found nothing). Returns None if every attempt failed (no internet, Semantic
    Scholar is down, still rate-limited after retrying, etc.) - the route checks for
    that None specifically so it can show "couldn't reach Semantic Scholar" instead of
    a confusing empty list.

    Without a personal API key, this request shares one rate-limit pool with every
    other unauthenticated Semantic Scholar user on the internet - so it's normal for
    it to occasionally get a 429 (rate limited) even though nothing is wrong with this
    app; see MAX_ATTEMPTS above for how that's retried before giving up. A free key
    (see SEMANTIC_SCHOLAR_API_KEY in .env.example) gives this app its own guaranteed 1
    request/second instead of competing for that shared pool - request one at
    https://www.semanticscholar.org/product/api#api-key if these errors keep showing
    up. Note that key is per-app, not per-person: if several people are testing against
    the same key/machine at the same time, they're still sharing that one guaranteed
    request/second between them, so occasional 429s during simultaneous testing are
    expected even with a key configured - each retries and usually succeeds a moment
    later.
    """
    headers = {"User-Agent": "ResearchLensAI-StudentProject (mailto:example@example.com)"}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    payload = None
    for attempt in range(MAX_ATTEMPTS):
        is_last_attempt = attempt == MAX_ATTEMPTS - 1
        try:
            response = requests.get(
                SEARCH_URL,
                params={"query": query, "limit": min(limit, MAX_LIMIT), "fields": FIELDS},
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as error:
            # Network-level failure (timeout, DNS, connection reset) - retry the same
            # way as a 429, since these are just as often transient.
            if is_last_attempt:
                print(f"[semantic_scholar_service] search failed after {MAX_ATTEMPTS} attempts: {error}")
                return None
            time.sleep(_seconds_to_wait(attempt, None))
            continue

        if response.status_code == 429:
            if is_last_attempt:
                print(f"[semantic_scholar_service] still rate-limited (429) after {MAX_ATTEMPTS} attempts")
                return None
            wait_seconds = _seconds_to_wait(attempt, response.headers.get("Retry-After"))
            print(f"[semantic_scholar_service] rate-limited (429) - retrying in {wait_seconds:.1f}s "
                  f"(attempt {attempt + 1}/{MAX_ATTEMPTS})")
            time.sleep(wait_seconds)
            continue

        try:
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            # A non-429 error (bad request, server error, unparseable body) - printing
            # here means the REAL reason shows up in the terminal where `python app.py`
            # is running, instead of disappearing silently. Not retried: these usually
            # won't resolve themselves the way a 429 or network blip does.
            print(f"[semantic_scholar_service] search failed: {error}")
            return None
        break  # got a usable payload - stop retrying

    if payload is None:
        return None

    results = []
    for paper in payload.get("data", []):
        author_names = ", ".join(
            a.get("name", "") for a in (paper.get("authors") or []) if a.get("name")
        )
        external_ids = paper.get("externalIds") or {}
        open_access_pdf = paper.get("openAccessPdf") or {}

        results.append({
            "external_id": paper.get("paperId"),
            "title": paper.get("title") or "Untitled",
            "authors": author_names,
            "year": paper.get("year"),
            "abstract": paper.get("abstract"),
            "doi": external_ids.get("DOI"),
            "url": paper.get("url"),
            "open_access_pdf_url": open_access_pdf.get("url"),
        })

    return results