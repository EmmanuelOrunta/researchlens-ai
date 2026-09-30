# services/evidence_service.py
#
# Evidence tracking (Sprint 5): makes an AI output link back to the SPECIFIC saved
# paper(s) - and the specific sentence within them - it actually drew from, instead
# of the reader having to trust an in-text "Huang (2025)" citation on faith. Three
# callers use this, each a different shape of the same underlying idea:
#
#   - stream_ask_literature()    - MULTI-paper: which of the project's papers did
#   - stream_synthesize_papers() -   this answer/synthesis actually draw from, and
#                                    what did each one say that grounds it?
#   - stream_summarize_paper()   - SINGLE-paper: this paper's summary always has
#                                    exactly six fixed paragraphs (see that
#                                    function) - which sentence of ITS OWN abstract/
#                                    text backs each paragraph?
#
# The mechanism is the same for both shapes: the system prompt asks the model to
# end its answer with a small machine-readable block, keyed by whichever number the
# model was already given (a "Paper N" label for the multi-paper case, a paragraph
# number 1-6 for the single-paper case) and containing one short, VERBATIM quote per
# key. This module strips that block back out of the visible text, parses it, and -
# critically - VERIFIES each quote actually appears in the exact source text the
# model was shown for that key, rather than trusting the model's word for it. A
# quote that doesn't verify is still shown (the model may have paraphrased rather
# than hallucinated, and hiding it would look like the app is hiding evidence), just
# labeled "not verified verbatim" instead of "verified" - see verified below.
#
# Deliberately NOT done here: anchoring a quote to a specific SENTENCE inside a long
# multi-paragraph answer. That would need the model to interleave markers throughout
# its prose while streaming, which is both a much less reliable ask for the model and
# far harder to strip live without visibly flickering - see EVIDENCE_BLOCK_MARKER
# below and static/js/app.js's stripEvidenceMarker() for how today's simpler
# "one trailing block" design gets stripped cleanly even mid-stream.

import re

# The line the trailing block starts with. Chosen to be something that would never
# plausibly appear in the AI's own prose, so a plain "cut everything from the first
# occurrence of this onward" is a safe, cheap way to hide the (still-arriving) block
# from view WHILE the model is still streaming it - both here (build_*_evidence()
# below, for the final saved text) and in static/js/app.js's stripEvidenceMarker()
# (for the live "typing" text), which must stay a mirror of this exact string.
EVIDENCE_BLOCK_MARKER = "<<<EVIDENCE"
_EVIDENCE_BLOCK_END = "EVIDENCE>>>"

# One line inside the block: a key (paper number or paragraph number), a colon, and
# a quoted excerpt - e.g. `2: "improves recall by 14% over the baseline"`. Tolerant
# of straight or curly quotes and a little stray whitespace, since this is model
# output, not a format the app itself controls.
_EVIDENCE_LINE_RE = re.compile(r'^\s*(\d+)\s*:\s*[“"\'](.+?)[”"\']\s*$')

MAX_EVIDENCE_QUOTE_CHARS = 400  # a sentence or two, not a paragraph - see the prompt text below


def _multi_evidence_instruction() -> str:
    return (
        "\n\nAfter your answer, on new lines, add a machine-readable evidence "
        "block so the reader can verify exactly which papers backed it and where. "
        f"Start the block with the line {EVIDENCE_BLOCK_MARKER} on its own, then "
        "one line per paper you actually drew from (skip any paper you didn't "
        "meaningfully use), in the form:\n"
        "N: \"a short excerpt, quoted VERBATIM from that paper's own material "
        "given above, that supports what you wrote\"\n"
        "- where N is that paper's number from the numbered list above. Keep each "
        "quoted excerpt under roughly 30 words - just enough to show where the "
        "claim comes from, not the whole passage. Copy it EXACTLY as written above; "
        "never paraphrase or invent a quote. "
        f"End the block with the line {_EVIDENCE_BLOCK_END} on its own. Do not add "
        "anything after that line."
    )


def _single_evidence_instruction() -> str:
    return (
        "\n\nAfter the six paragraphs, on new lines, add a machine-readable "
        "evidence block so the reader can see exactly which sentence of the "
        f"source material each paragraph is grounded in. Start with "
        f"{EVIDENCE_BLOCK_MARKER} on its own line, then exactly six lines, one per "
        "paragraph in order:\n"
        "N: \"a short excerpt, quoted VERBATIM from the abstract/text given above, "
        "that supports paragraph N\"\n"
        "Keep each quoted excerpt under roughly 30 words. Copy it EXACTLY as "
        "written in the source text above - never paraphrase or invent a quote; if "
        "a paragraph genuinely has nothing to quote (e.g. it's a brief critical "
        "aside not drawn from a specific sentence), quote the closest supporting "
        f"sentence instead rather than skipping the line. End with "
        f"{_EVIDENCE_BLOCK_END} on its own line. Do not add anything after that line."
    )


MULTI_EVIDENCE_INSTRUCTION = _multi_evidence_instruction()
SINGLE_EVIDENCE_INSTRUCTION = _single_evidence_instruction()


def _extract_surname(full_name: str) -> str:
    parts = full_name.split()
    return parts[-1] if parts else full_name


def format_citation_label(authors, year) -> str:
    """
    The SAME "Huang (2025)" / "Smith and Lee (2023)" / "Chen et al. (2024)" style
    every system prompt in this app already asks the model to cite with - but
    computed here from the paper's own authors/year fields directly, for the
    evidence chip's label, rather than trusted from whatever text the model
    happened to write inline. paper.authors is stored as full "First Last" names
    joined by ", " (see services/semantic_scholar_service.py /
    services/openalex_service.py), so splitting on "," and taking each name's last
    word is the correct way to recover surnames here.
    """
    year_part = f" ({year})" if year else ""
    names = [n.strip() for n in (authors or "").split(",") if n.strip()]
    if not names:
        return "Unnamed source" + year_part
    surnames = [_extract_surname(name) for name in names]
    if len(surnames) == 1:
        label = surnames[0]
    elif len(surnames) == 2:
        label = f"{surnames[0]} and {surnames[1]}"
    else:
        label = f"{surnames[0]} et al."
    return f"{label}{year_part}" if year_part else label


def _normalize_for_match(text: str) -> str:
    """Lowercase, collapse whitespace, and fold curly quotes to straight ones, so a
    quote that differs from the source only in whitespace/quote-character style
    still verifies - this is meant to catch hallucination, not cosmetic drift."""
    text = (text or "").replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_quote(quote: str, source_text: str) -> bool:
    """True if `quote` appears verbatim (after light normalization) inside
    `source_text` - the exact text the model was shown for whatever it's citing.
    A quote that fails this isn't necessarily hallucinated (the model may have
    lightly paraphrased), so callers should still SHOW it, just labeled as not
    verified rather than silently dropped - see build_multi_paper_evidence() /
    build_paragraph_evidence() below."""
    quote = _normalize_for_match(quote)
    source_text = _normalize_for_match(source_text)
    return bool(quote) and bool(source_text) and quote in source_text


def extract_evidence_block(raw_text: str):
    """
    Splits `raw_text` into (clean_text, entries): clean_text is everything before
    the evidence block (what should actually be shown/stored as the answer),
    entries is an ordered list of (key: int, quote: str) parsed from inside the
    block. Tolerant of the model forgetting the closing EVIDENCE>>> line (still
    parses whatever came after the opening marker) and of an entirely missing
    block (returns the full text unchanged and an empty list) - a malformed or
    missing block should degrade to "no evidence shown", never a broken answer.
    """
    marker_index = raw_text.find(EVIDENCE_BLOCK_MARKER)
    if marker_index == -1:
        return raw_text.strip(), []

    clean_text = raw_text[:marker_index].rstrip()
    block = raw_text[marker_index + len(EVIDENCE_BLOCK_MARKER):]
    end_index = block.find(_EVIDENCE_BLOCK_END)
    if end_index != -1:
        block = block[:end_index]

    entries = []
    for line in block.splitlines():
        match = _EVIDENCE_LINE_RE.match(line)
        if not match:
            continue
        key = int(match.group(1))
        quote = match.group(2).strip()[:MAX_EVIDENCE_QUOTE_CHARS]
        if quote:
            entries.append((key, quote))
    return clean_text, entries


def build_multi_paper_evidence(raw_text: str, papers_in_order: list):
    """
    For stream_ask_literature() / stream_synthesize_papers(). `papers_in_order` is
    the SAME ordered list of dicts (each with "id"/"title"/"authors"/"year"/
    "capsule") used to build the "Paper 1: ...", "Paper 2: ..." block those prompts
    show the model - so entry key N here means exactly papers_in_order[N-1], with
    no separate id-guessing needed. Returns (clean_text, evidence): evidence is a
    list of {"paper_id", "label", "quote", "verified"} dicts, one per DISTINCT
    paper actually cited (a repeated or out-of-range paper number is silently
    skipped/deduplicated - never lets a malformed line surface as a UI error).
    """
    clean_text, raw_entries = extract_evidence_block(raw_text)
    evidence = []
    seen_paper_ids = set()
    for key, quote in raw_entries:
        index = key - 1
        if index < 0 or index >= len(papers_in_order):
            continue
        paper = papers_in_order[index]
        paper_id = paper.get("id")
        if paper_id is None or paper_id in seen_paper_ids:
            continue
        seen_paper_ids.add(paper_id)
        evidence.append({
            "paper_id": paper_id,
            "label": format_citation_label(paper.get("authors"), paper.get("year")),
            "quote": quote,
            "verified": verify_quote(quote, paper.get("capsule") or ""),
        })
    return clean_text, evidence


def build_paragraph_evidence(raw_text: str, source_text: str):
    """
    For stream_summarize_paper() - a SINGLE paper's evidence, keyed by which of the
    summary's six fixed paragraphs (1-6) each quote supports, verified against that
    same paper's own abstract/extracted text (`source_text` - exactly what the
    summary was generated from). Returns (clean_text, evidence_by_paragraph), the
    latter a dict {paragraph_number: {"quote", "verified"}} - paragraphs the model
    didn't cover (a missing/malformed line) simply have no entry, so the template
    can render that paragraph without an evidence toggle rather than a broken one.
    """
    clean_text, raw_entries = extract_evidence_block(raw_text)
    evidence_by_paragraph = {}
    for key, quote in raw_entries:
        if key < 1 or key in evidence_by_paragraph:
            continue
        evidence_by_paragraph[key] = {
            "quote": quote,
            "verified": verify_quote(quote, source_text or ""),
        }
    return clean_text, evidence_by_paragraph


def attach_paper_titles(evidence_list: list, papers_by_id: dict) -> list:
    """
    Enriches a build_multi_paper_evidence() list with each cited paper's own
    title, so templates (ask_literature.html, paper_synthesis.html) can link
    straight to the source paper without doing their own lookup. `papers_by_id`
    is whatever {paper.id: paper} mapping the route already has on hand for the
    current project.

    A cited paper_id that's no longer in `papers_by_id` (removed from the
    project, or the project's library changed since the answer was generated)
    degrades gracefully: the entry keeps its label/quote/verified fields and
    gets "title": None, so the template can still show the citation text but
    skip rendering a broken link - never a crash, never a dropped citation.
    """
    enriched = []
    for entry in evidence_list:
        paper = papers_by_id.get(entry.get("paper_id"))
        enriched.append(dict(entry, title=paper.title if paper is not None else None))
    return enriched
