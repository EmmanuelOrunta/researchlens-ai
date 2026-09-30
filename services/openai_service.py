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
from services import evidence_service

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


def _stream(system_prompt: str, user_content: str, max_input_chars: int = MAX_INPUT_CHARS):
    """
    Shared plumbing for every feature below - the streaming counterpart of what used
    to be a single request/response call. Confirms a key is configured, opens a
    streaming call to the Responses API, and yields plain dicts a route can forward
    live to the browser for a ChatGPT-style "typing" effect (see
    routes/papers_routes.py's summarize_stream() / generate_relevance_stream(), and
    static/js/app.js for how the page consumes this):

    `max_input_chars` defaults to MAX_INPUT_CHARS (right for every single-paper or
    single-selection call below, where the source text is the biggest, least
    predictable piece and everything else is short and fixed). stream_ask_literature()
    passes a larger value instead, because IT already caps its own pieces (papers
    block, history, question) to fixed budgets before assembling user_content - so
    truncating here again would only risk cutting into the assembled text this
    slice never needs to touch (see that function's own comment for why the ORDER
    of truncation matters there).

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
                {"role": "user", "content": user_content[:max_input_chars]},
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


# --- Evidence tracking (Sprint 5) - see services/evidence_service.py ---
#
# Two thin wrappers around _stream() above, one per evidence "shape" (which paper,
# vs. where in the one paper - see that module's own top-of-file comment). Every
# {"delta"}/{"error"} event passes through completely unchanged - the trailing
# evidence block a delta might still be mid-way through arriving is hidden from the
# LIVE view client-side instead (static/js/app.js's stripEvidenceMarker()), not
# here, since re-buffering deltas server-side would defeat the point of streaming.
# Only the terminal {"done"} event needs anything done to it: strip the block out
# of the text a caller is about to persist/show, and attach whatever evidence
# parsed out of it under a new "evidence" key.

def _stream_with_multi_paper_evidence(system_prompt: str, user_content: str, papers: list,
                                       max_input_chars: int = MAX_INPUT_CHARS):
    for event in _stream(system_prompt, user_content, max_input_chars=max_input_chars):
        if event.get("done"):
            clean_text, evidence = evidence_service.build_multi_paper_evidence(event["text"], papers)
            yield {"done": True, "text": clean_text or event["text"], "evidence": evidence}
        else:
            yield event


def _stream_with_paragraph_evidence(system_prompt: str, user_content: str, source_text: str,
                                     max_input_chars: int = MAX_INPUT_CHARS):
    for event in _stream(system_prompt, user_content, max_input_chars=max_input_chars):
        if event.get("done"):
            clean_text, evidence = evidence_service.build_paragraph_evidence(event["text"], source_text)
            yield {"done": True, "text": clean_text or event["text"], "evidence": evidence}
        else:
            yield event


def stream_summarize_paper(title: str, authors: str, year, text: str):
    """
    Summarize a paper's abstract (or extracted PDF text, for an upload) into a full,
    structured literature-review-style summary (roughly 300-500 words, across exactly
    six paragraphs - author(s)/research question, problem statement and proposed
    solution, methodology, results/findings, conclusion, and critical reflection, each
    separated by a blank line so the UI can render them as distinct paragraphs - see
    templates/project_paper_detail.html and static/js/app.js), yielded incrementally
    as it's generated - see _stream() above for the exact event shapes.
    `text` should be paper.abstract or paper.extracted_text - whichever the caller
    has; this function doesn't know or care which. `authors` and `year` (paper.authors
    / paper.year - year may be None) are used only for the opening in-text citation -
    see the system prompt below.
    """
    if not (text or "").strip():
        yield {"error": "This paper has no abstract or extracted text to summarize."}
        return

    system_prompt = (
        "You write structured, in-depth summaries of academic research papers for a "
        "student doing a literature review. Write roughly 300-500 words of academic "
        "prose organized into EXACTLY six paragraphs, in this order, with no "
        "headings, labels, bullet points, numbered lists, or markdown formatting "
        "anywhere in the output - each paragraph should read as plain prose, and the "
        "only structure should come from where one paragraph ends and the next "
        "begins. Separate every paragraph from the next with a blank line (i.e. two "
        "newline characters), and do not put a blank line anywhere except between "
        "these six paragraphs:\n\n"
        "1. Author(s) and research question: open with a standard academic in-text "
        "citation lead-in naming the paper's author(s) and publication year if given "
        "(e.g. 'Huang (2025) investigates...' or 'Smith et al. (2023) examines...' - "
        "use the surname(s) only, and 'et al.' for three or more authors), then "
        "state the paper's research question or what it investigates. If no year is "
        "given, drop the year rather than inventing one; if no authors are given, "
        "open with the paper's subject instead of a citation.\n"
        "2. Problem statement and proposed solution: the gap, limitation, or "
        "challenge in existing approaches that motivates this paper, and what the "
        "paper proposes to address it.\n"
        "3. Methodology: the actual methods, techniques, models, datasets, or "
        "experimental design used - in enough detail that a reader understands the "
        "approach, not just that one exists.\n"
        "4. Results/findings: the paper's key findings, specific enough to "
        "understand what was actually shown, not just that 'results were "
        "positive.'\n"
        "5. Conclusion: the paper's own stated conclusion or takeaway - what the "
        "authors argue the results mean.\n"
        "6. Critical reflection: a brief, neutral critical assessment of the "
        "paper's contribution and any notable limitation or gap it leaves "
        "unaddressed (e.g. practical, cost, generalizability, or scope concerns) - "
        "written in the third person as an assessment of the paper's work, never as "
        "a first-person opinion ('I found', 'in my opinion', etc.).\n\n"
        "Base every claim only on the title/authors/year and abstract or text "
        "provided below - never invent methodology, results, or findings the source "
        "text doesn't support. If the abstract or text is too thin to support one of "
        "the six paragraphs above with real substance, keep that paragraph short and "
        "factual rather than filling the gap with invented specifics - but still "
        "produce exactly six paragraphs, separated by blank lines, every time."
        + evidence_service.SINGLE_EVIDENCE_INSTRUCTION
    )
    authors_line = authors or "Not specified"
    year_line = year if year else "Not specified"
    user_content = (
        f"Title: {title}\n"
        f"Authors: {authors_line}\n"
        f"Year: {year_line}\n\n"
        f"Abstract/text:\n{text}"
    )
    yield from _stream_with_paragraph_evidence(system_prompt, user_content, text)


def stream_synthesize_papers(project_title: str, research_question: str, papers: list):
    """
    Paper Synthesis (Sprint 4): a single flowing, multi-paragraph narrative across
    SEVERAL selected papers - summarizing, synthesizing, comparing, and critiquing them
    together, the way a literature review's own "Synthesis Review" section would (as
    opposed to the Literature Matrix's row-by-row structured fields, or
    stream_summarize_paper()'s six fixed paragraphs about one paper alone). Yielded
    incrementally as it's generated - see _stream() above for the exact event shapes.

    `papers` is a list of dicts, one per paper the user selected, each with "title",
    "authors", "year", and "capsule" (a compact description of the paper - see
    services/paper_service.py's build_synthesis_capsule(), which prefers the Literature
    Matrix's fields when they exist and falls back to the abstract). The route calling
    this (routes/papers_routes.py's synthesis_stream()) is responsible for requiring at
    least two papers before calling here - a "synthesis" of one paper isn't meaningful,
    which is also why this errors below rather than silently degrading to something
    that reads like a single-paper summary.
    """
    if len(papers) < 2:
        yield {"error": "Select at least 2 papers to synthesize."}
        return

    system_prompt = (
        "You are helping a student write the \"Synthesis Review\" section of a "
        "literature review, drawing on several academic papers they have selected. "
        "Write a single flowing, cohesive piece of academic prose - between 5 and 8 "
        "paragraphs, with NO headings, labels, bullet points, numbered lists, or "
        "markdown formatting anywhere in the output; each paragraph should read as "
        "plain prose, and the only structure should come from where one paragraph "
        "ends and the next begins. Separate every paragraph from the next with a "
        "blank line (i.e. two newline characters), and do not put a blank line "
        "anywhere except between paragraphs.\n\n"
        "The papers are listed below, each with its title, authors, and year, plus "
        "either its methodology/sample/findings/limitations or its abstract. "
        "Whenever you refer to a specific paper, cite it with a standard academic "
        "in-text citation built from its own authors/year given below (surname(s) "
        "and year - e.g. 'Huang (2025)' for one author, 'Smith and Lee (2023)' for "
        "two, 'Chen et al. (2024)' for three or more; if no year is given for a "
        "paper, cite it by surname(s) only). Never invent a citation the list below "
        "doesn't support, and never discuss a paper that isn't in the list.\n\n"
        "Across the paragraphs, your synthesis should:\n"
        "1. Open by identifying the overarching trend, theme, or problem that "
        "connects these papers - the shared question or gap they're all responding "
        "to.\n"
        "2. Compare and contrast specific papers directly, citing them by name: "
        "where do they agree, where do their approaches, methods, or findings "
        "diverge, and what does each contribute that the others don't?\n"
        "3. Identify what the papers collectively rely on (shared data types, "
        "methods, or assumptions) and what challenges or limitations recur across "
        "more than one of them.\n"
        "4. Critique the body of work as a whole - what's missing, under-explored, "
        "or narrow in scope across these papers TOGETHER, as a genuine assessment "
        "of the collective gap, not a list of each paper's individual flaws "
        "restated one by one.\n"
        "5. Close by stating what this body of literature establishes overall, and "
        "- only if a project title or research question is given below - how it "
        "relates to or informs that project specifically; otherwise just close on "
        "the literature's own collective contribution.\n\n"
        "Base every claim only on the information given below for each paper - "
        "never invent methodology, findings, or details a paper's entry doesn't "
        "support. Write in the third person as a neutral academic assessment, never "
        "in the first person ('I think', 'in my opinion')."
        + evidence_service.MULTI_EVIDENCE_INSTRUCTION
    )

    context_lines = []
    if project_title:
        context_lines.append(f"Project: {project_title}")
    if research_question:
        context_lines.append(f"Research question: {research_question}")
    context_block = ("\n".join(context_lines) + "\n\n") if context_lines else ""

    papers_block = "\n\n".join(
        f"Paper {i + 1}:\n"
        f"Title: {paper['title']}\n"
        f"Authors: {paper['authors'] or 'Not specified'}\n"
        f"Year: {paper['year'] if paper['year'] else 'Not specified'}\n"
        f"{paper['capsule']}"
        for i, paper in enumerate(papers)
    )
    user_content = f"{context_block}Papers:\n\n{papers_block}"
    yield from _stream_with_multi_paper_evidence(system_prompt, user_content, papers)


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


def stream_extract_matrix_fields(title: str, authors: str, year, text: str):
    """
    Extract the four Literature Matrix fields from a paper's abstract (or extracted PDF
    text) - Methodology, Sample, Findings, Limitations, in that fixed order, each as a
    short plain-prose paragraph separated by a blank line (same "exactly N paragraphs,
    blank-line-separated" contract as stream_summarize_paper() above, just with four
    fields instead of six paragraphs) - see templates/literature_matrix.html and
    static/js/app.js's [data-stream-url] handler (data-targets) for how the four
    paragraphs get split back apart into the matrix table's four separate cells.
    `text` should be paper.abstract or paper.extracted_text, same as
    stream_summarize_paper(). The result is AI-extracted but directly user-editable
    afterwards (see routes/papers_routes.py's edit_matrix_fields()), unlike the AI
    Summary.
    """
    if not (text or "").strip():
        yield {"error": "This paper has no abstract or extracted text to extract from."}
        return

    system_prompt = (
        "You extract structured literature-review fields from an academic paper for a "
        "student building a comparison matrix across several papers. Produce EXACTLY "
        "four short paragraphs of plain prose, in this order, with no headings, "
        "labels, bullet points, numbered lists, or markdown formatting anywhere in the "
        "output - each paragraph should be 1-3 sentences, concise enough to sit in a "
        "table cell. Separate every paragraph from the next with a blank line (i.e. "
        "two newline characters), and do not put a blank line anywhere except between "
        "these four paragraphs:\n\n"
        "1. Methodology: the actual methods, techniques, models, or experimental "
        "design used.\n"
        "2. Sample: the dataset, participants, materials, or study setting the paper "
        "draws on - its size or scope if given. If the paper is theoretical or "
        "doesn't describe an empirical sample, say so briefly instead of inventing "
        "one.\n"
        "3. Findings: the paper's key results, specific enough to understand what was "
        "actually shown.\n"
        "4. Limitations: the paper's own stated limitations, or - only if the paper "
        "states none itself - a brief, neutral, fair assessment of a notable gap "
        "(scope, generalizability, sample size, etc.), written in the third person, "
        "never as a first-person opinion.\n\n"
        "Base every claim only on the title/authors/year and abstract or text "
        "provided below - never invent methodology, sample details, or findings the "
        "source text doesn't support. If the source text is too thin to support one "
        "of the four fields with real substance, keep that paragraph short and "
        "factual rather than filling the gap with invented specifics - but still "
        "produce exactly four paragraphs, separated by blank lines, every time."
    )
    authors_line = authors or "Not specified"
    year_line = year if year else "Not specified"
    user_content = (
        f"Title: {title}\n"
        f"Authors: {authors_line}\n"
        f"Year: {year_line}\n\n"
        f"Abstract/text:\n{text}"
    )
    yield from _stream(system_prompt, user_content)


# Ask the Literature (Sprint 4) assembles more pieces into user_content than any
# call above - every saved paper's capsule, several turns of conversation history,
# AND the new question - so each piece gets its own smaller character budget,
# applied BEFORE assembly, rather than leaning on _stream()'s own MAX_INPUT_CHARS
# truncation the way every function above does. That default truncation keeps the
# FRONT of user_content and cuts the END, which is exactly backwards for this
# call: the new question belongs at the very end (so it reads naturally after the
# conversation history), and if the assembled text ever ran long, a plain end-cut
# would risk slicing off the question itself rather than some of the (less
# critical) context around it. Capping each piece up front, then passing a ceiling
# comfortably larger than their combined worst case (see ASK_LITERATURE_INPUT_CHARS
# below) to _stream(), means its own slice is just a safety net that in practice
# never actually triggers.
MAX_PAPERS_BLOCK_CHARS = 8_000
MAX_HISTORY_BLOCK_CHARS = 4_000
MAX_QUESTION_CHARS = 2_000
ASK_LITERATURE_INPUT_CHARS = MAX_PAPERS_BLOCK_CHARS + MAX_HISTORY_BLOCK_CHARS + MAX_QUESTION_CHARS + 2_000


def stream_ask_literature(project_title: str, research_question: str, papers: list,
                           history: list, question: str):
    """
    Ask the Literature (Sprint 4): a running Q&A conversation, scoped to one
    project, answered using EVERY paper currently saved to it - unlike Paper
    Synthesis, which lets a user hand-pick a subset (see
    routes/papers_routes.py's ask_literature_stream()). Yielded incrementally as
    it's generated - see _stream() above for the exact event shapes.

    `papers` is a list of dicts shaped like stream_synthesize_papers()'s own
    ("title", "authors", "year", "capsule" - see services/paper_service.py's
    build_synthesis_capsule()). `history` is the conversation so far, oldest first,
    as a list of {"role": "user"|"assistant", "content": "..."} dicts (see
    services/literature_chat_service.py's get_recent_history_for_prompt()) - it
    does NOT include the new question, which is passed separately as `question` so
    it can be placed, and guaranteed to survive truncation, at the very end of the
    prompt (see the character budgets above).
    """
    if not papers:
        yield {"error": "Save at least one paper to this project first, then you can ask questions about it."}
        return
    if not (question or "").strip():
        yield {"error": "Type a question first."}
        return

    system_prompt = (
        "You are a research assistant helping a student explore the papers they've "
        "saved to one research project, by answering their questions using ONLY "
        "the paper information given below - never outside knowledge, and never a "
        "paper that isn't listed. Ground every claim in a specific paper, citing it "
        "with a standard academic in-text citation built from the authors/year "
        "given for it below (surname(s) and year - e.g. 'Huang (2025)' for one "
        "author, 'Smith and Lee (2023)' for two, 'Chen et al. (2024)' for three or "
        "more; if no year is given for a paper, cite it by surname(s) only). Never "
        "invent a citation, a paper, a finding, or a detail the material below "
        "doesn't support. If the papers don't contain enough information to answer "
        "confidently, say so plainly rather than guessing.\n\n"
        "This may be a follow-up to earlier questions in the same conversation "
        "(given below, if any) - answer only the NEW question at the end, using "
        "the earlier exchange purely for context (e.g. resolving 'it' or 'the "
        "second paper'), never as something to re-answer from scratch.\n\n"
        "Write 1-4 short paragraphs of plain academic prose - no headings, labels, "
        "bullet points, numbered lists, or markdown formatting anywhere in the "
        "output. If you write more than one paragraph, separate each from the next "
        "with a blank line (i.e. two newline characters), and do not put a blank "
        "line anywhere else."
        + evidence_service.MULTI_EVIDENCE_INSTRUCTION
    )

    context_lines = []
    if project_title:
        context_lines.append(f"Project: {project_title}")
    if research_question:
        context_lines.append(f"Research question: {research_question}")
    context_block = ("\n".join(context_lines) + "\n\n") if context_lines else ""

    papers_block = "\n\n".join(
        f"Paper {i + 1}:\n"
        f"Title: {paper['title']}\n"
        f"Authors: {paper['authors'] or 'Not specified'}\n"
        f"Year: {paper['year'] if paper['year'] else 'Not specified'}\n"
        f"{paper['capsule']}"
        for i, paper in enumerate(papers)
    )[:MAX_PAPERS_BLOCK_CHARS]

    history_block = ""
    if history:
        history_lines = [
            f"{'Q' if turn['role'] == 'user' else 'A'}: {turn['content']}"
            for turn in history
        ]
        history_block = ("Conversation so far:\n" + "\n".join(history_lines))[:MAX_HISTORY_BLOCK_CHARS] + "\n\n"

    question_block = f"New question: {(question or '').strip()[:MAX_QUESTION_CHARS]}"

    user_content = f"{context_block}Papers:\n\n{papers_block}\n\n{history_block}{question_block}"
    yield from _stream_with_multi_paper_evidence(
        system_prompt, user_content, papers, max_input_chars=ASK_LITERATURE_INPUT_CHARS
    )
