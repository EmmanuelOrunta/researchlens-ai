# services/openai_service.py
#
# Talks to OpenAI's API for two Sprint 3 features: summarizing a paper's abstract (or
# extracted PDF text, for an upload), and analysing how relevant a saved paper is to a
# project's research question. Both are lightweight, per-paper calls - not a heavy
# reasoning task - so this uses OpenAI's cheapest current model rather than a flagship
# one; see MODEL below.
#
# Nothing in this file touches the database - the routes that call these functions are
# responsible for storing whatever comes back (paper.summary / saved_paper.relevance_
# analysis), the same separation semantic_scholar_service.py and openalex_service.py
# already use for search results.

import os
from openai import OpenAI, OpenAIError

# OpenAI's cheapest/fastest current model (as of Sept 2026), built for high-volume,
# latency-sensitive work like this rather than complex reasoning - see
# https://platform.openai.com/docs/models. If OpenAI retires this model name, swap it
# in this one place rather than hunting through every call site.
MODEL = "gpt-5.6-luna"

# Keeps a giant uploaded PDF's extracted text (up to 200,000 chars - see
# pdf_service.py's MAX_EXTRACTED_CHARS) from turning one summarization call into a
# huge, slow, and needlessly expensive request. This many characters is already
# several times a typical paper's abstract + introduction, which is plenty for a
# summary or a relevance judgement.
MAX_INPUT_CHARS = 12_000


def is_configured() -> bool:
    """
    True if an OPENAI_API_KEY is set. Routes check this before even trying a request,
    so a missing key shows a clear "add a key" message instead of a confusing failed-
    request error - the same pattern .env.example's SEMANTIC_SCHOLAR_API_KEY guidance
    uses.
    """
    return bool(os.environ.get("OPENAI_API_KEY"))


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _run(system_prompt: str, user_content: str):
    """
    Shared plumbing for both features below: confirms a key is configured, calls the
    Responses API (OpenAI's current recommended API for new integrations, in place of
    the older Chat Completions API), and turns any failure into a (None, message) pair
    the routes can flash straight to the user instead of a stack trace.

    Returns (text, error) - exactly one of the two is ever set.
    """
    if not is_configured():
        return None, "Add a free OPENAI_API_KEY in .env to use AI analysis - see .env.example."

    try:
        client = _client()
        response = client.responses.create(
            model=MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content[:MAX_INPUT_CHARS]},
            ],
        )
        text = (response.output_text or "").strip()
        if not text:
            return None, "OpenAI returned an empty response - try again."
        return text, None
    except OpenAIError as error:
        # Printing here means the REAL reason (invalid key, rate limit, no credit,
        # OpenAI down, etc.) shows up in your terminal where `python app.py` is
        # running, instead of disappearing silently - worth checking there if this
        # keeps failing.
        print(f"[openai_service] request failed: {error}")
        return None, (
            "OpenAI didn't respond to this request (this usually means an invalid "
            "key, no billing set up, or a rate limit) - check the terminal running "
            "`python app.py` for the real error, and try again."
        )
    except Exception as error:
        print(f"[openai_service] unexpected error: {error}")
        return None, "Something went wrong talking to OpenAI - try again."


def summarize_paper(title: str, text: str):
    """
    Summarize a paper's abstract (or extracted PDF text, for an upload) into a few
    plain-language sentences. `text` should be paper.abstract or paper.extracted_text -
    whichever the caller has; this function doesn't know or care which.

    Returns (summary, error) - summary is None if error is set.
    """
    if not (text or "").strip():
        return None, "This paper has no abstract or extracted text to summarize."

    system_prompt = (
        "You summarize academic research papers for a student doing a literature "
        "review. Write a concise, plain-language summary in 3-5 sentences covering: "
        "what the paper studies, its method at a high level, and its main finding or "
        "contribution. Write plain prose only - no headings, no bullet points, no "
        "markdown formatting."
    )
    user_content = f"Title: {title}\n\nAbstract/text:\n{text}"
    return _run(system_prompt, user_content)


def analyze_relevance(paper_title: str, paper_text: str, research_question: str,
                       research_field: str, keywords: str):
    """
    Assess how relevant a saved paper is to a project's research question. This is
    intentionally scoped to one saved paper against one project's stated question/
    field/keywords - not a search across the whole library - matching the project
    plan's boundary that this app assists a researcher's own judgement rather than
    acting as an autonomous one.

    Returns (analysis, error) - analysis is None if error is set.
    """
    if not (research_question or research_field or keywords):
        return None, (
            "Add a research question, field, or keywords to this project first "
            "(Edit Project) so relevance has something to be judged against."
        )
    if not (paper_text or "").strip():
        return None, "This paper has no abstract or extracted text to analyse."

    system_prompt = (
        "You help a student doing a literature review judge how relevant a paper is "
        "to their research project. Given the project's research question, field, and "
        "keywords, plus a paper's title and abstract, write a short paragraph (2-4 "
        "sentences) explaining specifically how (or whether) the paper relates to the "
        "project - what it would contribute as evidence, a method, theoretical "
        "grounding, or background. If it's only tangentially related or not "
        "genuinely relevant, say so plainly rather than overstating a connection. "
        "Write plain prose only - no headings, no bullet points, no markdown "
        "formatting. End with one line in exactly this format: 'Relevance: X/5' where "
        "X is your rating from 1 (not relevant) to 5 (highly relevant)."
    )
    user_content = (
        f"Project research question: {research_question or 'Not specified'}\n"
        f"Project research field: {research_field or 'Not specified'}\n"
        f"Project keywords: {keywords or 'Not specified'}\n\n"
        f"Paper title: {paper_title}\n"
        f"Paper abstract/text:\n{paper_text}"
    )
    return _run(system_prompt, user_content)
