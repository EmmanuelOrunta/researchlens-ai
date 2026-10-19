# tests/test_ai_stream_guards.py
#
# Sprint 5, roadmap item 6 (continued): every AI-analysis function in
# services/openai_service.py is a generator that does its own validation BEFORE
# ever trying to contact OpenAI - see each function's own guard clauses (empty
# text, too few papers, no research context, etc.) and _stream()'s own
# is_configured() check right at its top. That means two very important
# behaviors are fully testable WITHOUT a live API key, a network call, or
# spending a single cent of OpenAI credit:
#
#   1. Every "missing required input" case yields exactly one clear {"error": ...}
#      and stops - never half-starts a request with bad input.
#   2. Every AI feature fails with one clear, actionable {"error": ...} message
#      when OPENAI_API_KEY isn't set - never hangs, never throws a raw exception
#      that would show the user a stack trace instead of a plain English reason.
#
# This is "AI accuracy testing" in the sense that matters most before a live
# demo: the app is honest and predictable about ITS OWN limits, in every one of
# its five AI entry points, independent of whatever OpenAI itself does on a
# given day. Whether a live, successful AI response is factually good is a
# separate, human judgement call - see docs/Sprint5_AI_Accuracy_Checklist.md.
#
# IMPORTANT: MissingApiKeyGuardTests below deliberately removes OPENAI_API_KEY
# from the environment for the duration of each test, even if your real .env
# has a real key in it, and restores it afterwards. This guarantees these tests
# never accidentally make a real, billed OpenAI request.

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.openai_service import (
    stream_summarize_paper,
    stream_analyze_relevance,
    stream_extract_matrix_fields,
    stream_synthesize_papers,
    stream_ask_literature,
)

VALID_PAPER = {"id": 1, "title": "A Real Paper", "authors": "Jane Smith", "year": 2024,
                "capsule": "Abstract: a real, non-empty capsule of text."}
VALID_PAPERS_FOR_SYNTHESIS = [
    VALID_PAPER,
    {"id": 2, "title": "A Second Real Paper", "authors": "Alex Chen", "year": 2025,
     "capsule": "Abstract: another real, non-empty capsule of text."},
]


def _only_event(generator):
    """Collects every event a stream function yields and asserts there's exactly
    one - every guard clause in this file is a stop-immediately case, so a well-
    behaved generator should never yield anything after its single error."""
    events = list(generator)
    assert len(events) == 1, f"expected exactly 1 event, got {len(events)}: {events}"
    return events[0]


class MissingInputGuardTests(unittest.TestCase):
    """None of these ever reach is_configured() or OpenAI at all - they fail on
    the input itself, before that point, so these run regardless of whether a
    real OPENAI_API_KEY is present in your environment."""

    def test_summarize_paper_with_no_text(self):
        event = _only_event(stream_summarize_paper("A Paper", "Jane Smith", 2024, ""))
        self.assertIn("error", event)
        self.assertIn("no abstract or extracted text", event["error"])

    def test_summarize_paper_with_whitespace_only_text(self):
        event = _only_event(stream_summarize_paper("A Paper", "Jane Smith", 2024, "   \n  "))
        self.assertIn("error", event)

    def test_extract_matrix_fields_with_no_text(self):
        event = _only_event(stream_extract_matrix_fields("A Paper", "Jane Smith", 2024, None))
        self.assertIn("error", event)

    def test_analyze_relevance_with_no_research_context(self):
        event = _only_event(stream_analyze_relevance(
            "A Paper", "Some paper text.", research_question="", research_field="", keywords="",
        ))
        self.assertIn("error", event)
        self.assertIn("research question", event["error"])

    def test_analyze_relevance_with_no_paper_text(self):
        event = _only_event(stream_analyze_relevance(
            "A Paper", "", research_question="Does X affect Y?", research_field="", keywords="",
        ))
        self.assertIn("error", event)
        self.assertIn("no abstract or extracted text", event["error"])

    def test_synthesize_papers_with_zero_papers(self):
        event = _only_event(stream_synthesize_papers("A Project", "A question?", []))
        self.assertIn("at least 2", event["error"])

    def test_synthesize_papers_with_one_paper(self):
        event = _only_event(stream_synthesize_papers("A Project", "A question?", [VALID_PAPER]))
        self.assertIn("at least 2", event["error"])

    def test_ask_literature_with_no_saved_papers(self):
        event = _only_event(stream_ask_literature("A Project", "A question?", [], [], "What do the papers say?"))
        self.assertIn("Save at least one paper", event["error"])

    def test_ask_literature_with_an_empty_question(self):
        event = _only_event(stream_ask_literature("A Project", "A question?", [VALID_PAPER], [], "   "))
        self.assertIn("Type a question first", event["error"])


class MissingApiKeyGuardTests(unittest.TestCase):
    """Every case here has otherwise-VALID input - it passes every guard above
    and reaches _stream()'s is_configured() check, which is where it should stop
    when no key is set. This is the single most important thing to verify before
    a live demo: if OPENAI_API_KEY is missing or wrong, every AI feature should
    say so plainly rather than freezing the page or showing a crash."""

    def setUp(self):
        self._real_key = os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        if self._real_key is not None:
            os.environ["OPENAI_API_KEY"] = self._real_key

    def _assert_clean_key_error(self, generator):
        event = _only_event(generator)
        self.assertIn("error", event)
        self.assertIn("OPENAI_API_KEY", event["error"])
        return event

    def test_summarize_paper_without_a_key(self):
        self._assert_clean_key_error(
            stream_summarize_paper("A Paper", "Jane Smith", 2024, "A real abstract with real content.")
        )

    def test_analyze_relevance_without_a_key(self):
        self._assert_clean_key_error(
            stream_analyze_relevance("A Paper", "Real paper text.", "Does X affect Y?", "A Field", "keyword")
        )

    def test_extract_matrix_fields_without_a_key(self):
        self._assert_clean_key_error(
            stream_extract_matrix_fields("A Paper", "Jane Smith", 2024, "A real abstract with real content.")
        )

    def test_synthesize_papers_without_a_key(self):
        self._assert_clean_key_error(
            stream_synthesize_papers("A Project", "A question?", VALID_PAPERS_FOR_SYNTHESIS)
        )

    def test_ask_literature_without_a_key(self):
        self._assert_clean_key_error(
            stream_ask_literature("A Project", "A question?", [VALID_PAPER], [], "What do the papers say?")
        )


if __name__ == "__main__":
    unittest.main()
