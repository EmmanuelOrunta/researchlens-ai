# tests/test_evidence_service.py
#
# Sprint 5, roadmap item 6 (partial): "Test AI analysis - verify summarisation,
# relevance analysis, paper comparison..." The part of "AI analysis" we can actually
# verify automatically, without a live OpenAI key or a real network call, is the
# Evidence Tracking mechanism itself (services/evidence_service.py) - the code that
# checks whether an AI-claimed quote is REALLY in the source text. That logic is pure
# Python with no AI call involved, so it's exactly the kind of thing an automated test
# should cover. Actually spot-checking whether a live AI-generated summary is
# *factually* good is a human judgement call - see docs/Sprint5_AI_Accuracy_Checklist.md
# instead.

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import evidence_service as es


class VerifyQuoteTests(unittest.TestCase):

    def test_exact_quote_is_verified(self):
        source = "This study surveyed 400 students and faculty across six institutions."
        self.assertTrue(es.verify_quote("surveyed 400 students and faculty", source))

    def test_quote_not_present_is_not_verified(self):
        source = "This study surveyed 400 students and faculty across six institutions."
        self.assertFalse(es.verify_quote("interviewed 900 participants", source))

    def test_curly_vs_straight_quotes_still_match(self):
        source = 'The authors call this "a widening policy gap."'
        self.assertTrue(es.verify_quote("a widening policy gap", source))

    def test_case_and_extra_whitespace_are_ignored(self):
        source = "Findings were  CONSISTENT   across   all   three   cohorts."
        self.assertTrue(es.verify_quote("consistent across all three cohorts", source))

    def test_empty_quote_or_source_is_never_verified(self):
        self.assertFalse(es.verify_quote("", "some real text"))
        self.assertFalse(es.verify_quote("a real quote", ""))


class ExtractEvidenceBlockTests(unittest.TestCase):

    def test_splits_clean_text_from_the_hidden_block(self):
        raw = (
            "This is the visible answer.\n\n"
            "<<<EVIDENCE\n"
            '1: "a supporting quote"\n'
            "EVIDENCE>>>"
        )
        clean_text, entries = es.extract_evidence_block(raw)
        self.assertEqual(clean_text, "This is the visible answer.")
        self.assertEqual(entries, [(1, "a supporting quote")])

    def test_missing_block_returns_the_whole_text_with_no_entries(self):
        raw = "Just a normal answer with no evidence block at all."
        clean_text, entries = es.extract_evidence_block(raw)
        self.assertEqual(clean_text, raw)
        self.assertEqual(entries, [])

    def test_missing_closing_marker_still_parses_what_came_after_the_opener(self):
        raw = "Visible answer.\n\n<<<EVIDENCE\n2: \"still parsed\""
        clean_text, entries = es.extract_evidence_block(raw)
        self.assertEqual(clean_text, "Visible answer.")
        self.assertEqual(entries, [(2, "still parsed")])


class BuildMultiPaperEvidenceTests(unittest.TestCase):

    def setUp(self):
        self.papers = [
            {"id": 1, "authors": "Jane Smith", "year": 2023, "capsule": "The real source text for paper one."},
            {"id": 2, "authors": "Alex Chen", "year": 2024, "capsule": "The real source text for paper two."},
        ]

    def test_verified_and_unverified_quotes_are_both_kept(self):
        raw = (
            "An answer citing two papers.\n\n"
            "<<<EVIDENCE\n"
            '1: "the real source text for paper one"\n'
            '2: "a quote paper two never actually said"\n'
            "EVIDENCE>>>"
        )
        clean_text, evidence = es.build_multi_paper_evidence(raw, self.papers)
        self.assertEqual(clean_text, "An answer citing two papers.")
        by_paper = {entry["paper_id"]: entry for entry in evidence}
        self.assertTrue(by_paper[1]["verified"])
        self.assertFalse(by_paper[2]["verified"])
        self.assertEqual(by_paper[1]["label"], "Smith (2023)")

    def test_out_of_range_paper_number_is_silently_skipped(self):
        raw = 'Answer.\n\n<<<EVIDENCE\n9: "refers to a paper that was never given"\nEVIDENCE>>>'
        clean_text, evidence = es.build_multi_paper_evidence(raw, self.papers)
        self.assertEqual(evidence, [])

    def test_duplicate_paper_number_keeps_only_the_first(self):
        raw = (
            "Answer.\n\n<<<EVIDENCE\n"
            '1: "the real source text for paper one"\n'
            '1: "a second, different quote for the same paper"\n'
            "EVIDENCE>>>"
        )
        clean_text, evidence = es.build_multi_paper_evidence(raw, self.papers)
        self.assertEqual(len(evidence), 1)


class CitationLabelTests(unittest.TestCase):

    def test_single_author(self):
        self.assertEqual(es.format_citation_label("Jane Smith", 2023), "Smith (2023)")

    def test_two_authors(self):
        self.assertEqual(es.format_citation_label("Jane Smith, Alex Chen", 2024), "Smith and Chen (2024)")

    def test_three_or_more_authors_uses_et_al(self):
        self.assertEqual(
            es.format_citation_label("Jane Smith, Alex Chen, Priya Nair", 2025),
            "Smith et al. (2025)",
        )

    def test_missing_year_omits_the_parentheses(self):
        self.assertEqual(es.format_citation_label("Jane Smith", None), "Smith")


if __name__ == "__main__":
    unittest.main()
