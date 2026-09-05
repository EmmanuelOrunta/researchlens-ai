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


def _stream(system_prompt: str, user_content: str):
    """
    Shared plumbing for both features below - the streaming counterpart of what used
    to be a single request/response call. Confirms a key is configured, opens a
    streaming call to the Responses API, and yields plain dicts a route can forward
    live to the browser for a ChatGPT-style "typing" effect (see
    routes/papers_routes.py's summarize_stream() / generate_relevance_stream(), and
    static/js/app.js for how the page consumes this):

      - {"delta": "..."} for each incremental chunk of text as OpenAI generates it
      - {"error": "..."} if anything goes wrong, before or during generation - a
        caller should NOT persist anything to the database when this is yielded
      - {"done": True, "text": "<full text>"} once generation completes successfully -
        a caller should persist `text` at this point

    Deltas are accumulated manually into the final text (rather than relying on the
    SDK's own final-response helper) so this only depends on the one event shape
    ("response.output_text.delta") actually needed here.
    """
    if not is_configured():
        yield {"error": "Add a free OPENAI_API_KEY in .env to use AI analysis - see .env.example."}
        return

    full_text_parts = []
    try:
        client = _client()
        with client.responses.stream(
            model=MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content[:MAX_INPUT_CHARS]},
            ],
        ) as stream:
            for event in stream:
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    delta = getattr(event, "delta", "") or ""
                    if delta:
                        full_text_parts.append(delta)
                        yield {"delta": delta}
                elif event_type in ("error", "response.error"):
                    # The exact event type/attribute names for a mid-stream error
                    # aren't pinned down as precisely in OpenAI's docs as the success
                    # path is, so this checks both spellings seen in their examples
                    # rather than betting on one.
                    message = getattr(event, "message", None) or "an error"
                    print(f"[openai_service] stream reported an error event: {message}")
                    yield {"error": "OpenAI reported an error while generating - try again."}
                    return
                # Other event types (response.created, response.output_item.added,
                # response.completed, etc.) are just progress markers this doesn't
                # need - only the text deltas and a possible error matter here.
    except OpenAIError as error:
        # Printing here means the REAL reason (invalid key, rate limit, no credit,
        # OpenAI down, etc.) shows up in your terminal where `python app.py` is
        # running, instead of disappearing silently - worth checking there if this
        # keeps failing.
        print(f"[openai_service] streaming request failed: {error}")
        yield {"error": (
            "OpenAI didn't respond to this request (this usually means an invalid "
            "key, no billing set up, or a rate limit) - check the terminal running "
            "`python app.py` for the real error, and try again."
        )}
        return
    except Exception as error:
        print(f"[openai_service] unexpected streaming error: {error}")
        yield {"error": "Something went wrong talking to OpenAI - try again."}
        return

    full_text = "".join(full_text_parts).strip()
    if not full_text:
        yield {"error": "OpenAI returned an empty response - try again."}
        return
    yield {"done": True, "text": full_text}


def stream_summarize_paper(title: str, text: str):
    """
    Summarize a paper's abstract (or extracted PDF text, for an upload) into a few
    plain-language sentences, yielded incrementally as it's generated - see _stream()
    above for the exact event shapes. `text` should be paper.abstract or
    paper.extracted_text - whichever the caller has; this function doesn't know or
    care which.
    """
    if not (text or "").strip():
        yield {"error": "This paper has no abstract or extracted text to summarize."}
        return

    system_prompt = (
        "You summarize academic research papers for a student doing a literature "
        "review. Write a concise, plain-language summary in 3-5 sentences covering: "
        "what the paper studies, its method at a high level, and its main finding or "
        "contribution. Write plain prose only - no headings, no bullet points, no "
        "markdown formatting."
    )
    user_content = f"Title: {title}\n\nAbstract/text:\n{text}"
    yield from _stream(system_prompt, user_content)


def stream_analyze_relevance(paper_title: str, paper_text: str, research_question: str,
                              research_field: str, keywords: str):
    """
    Assess how relevant a saved paper is to a project's research question, yielded
    incrementally as it's generated - see _stream() above for the exact event shapes.
    This is intentionally scoped to one saved paper against one project's stated
    question/field/keywords - not a search across the whole library - matching the
    project plan's boundary that this app assists a researcher's own judgement rather
    than acting as an autonomous one.
    """
    if not (research_question or research_field or keywords):
        yield {"error": (
            "Add a research question, field, or keywords to this project first "
            "(Edit Project) so relevance has something to be judged against."
        )}
        return
    if not (paper_text or "").strip():
        yield {"error": "This paper has no abstract or extracted text to analyse."}
        return

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
    yield from _stream(system_prompt, user_content)
