# tests/test_matrix_and_synthesis.py
#
# Sprint 5, roadmap item 6 (continued): the Literature Matrix and Paper Synthesis
# building blocks that don't require a live AI call to verify - saving matrix fields,
# reducing a paper to its synthesis "capsule", and the 2-paper synthesis guard. See
# tests/test_evidence_service.py for the Evidence Tracking half of "AI analysis", and
# docs/Sprint5_AI_Accuracy_Checklist.md for the parts that genuinely need a human to
# read a live AI response and judge it.

from tests._dbtest import DatabaseTestCase
from services.database_service import get_session
from services.auth_service import create_user, hash_password
from services.project_service import create_project
from services.paper_service import (
    create_paper_from_search_result,
    set_paper_matrix_fields,
    build_synthesis_capsule,
)
from services.openai_service import stream_synthesize_papers


class MatrixFieldsTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.db = get_session()
        self.paper = create_paper_from_search_result(self.db, {
            "title": "A Paper About Something", "authors": "Jane Smith", "year": 2024,
            "abstract": "An abstract.", "source": "semantic_scholar",
        })

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def test_saving_matrix_fields_stamps_the_generated_at_time(self):
        self.assertIsNone(self.paper.matrix_generated_at)
        set_paper_matrix_fields(self.db, self.paper, "Survey design", "140 students", "Positive effect", "Single site")
        self.assertIsNotNone(self.paper.matrix_generated_at)
        self.assertEqual(self.paper.matrix_methodology, "Survey design")

    def test_blank_fields_are_stored_as_none_not_empty_strings(self):
        set_paper_matrix_fields(self.db, self.paper, "   ", "", "Positive effect", None)
        self.assertIsNone(self.paper.matrix_methodology)
        self.assertIsNone(self.paper.matrix_sample)
        self.assertEqual(self.paper.matrix_findings, "Positive effect")


class SynthesisCapsuleTests(DatabaseTestCase):

    def setUp(self):
        super().setUp()
        self.db = get_session()

    def tearDown(self):
        self.db.close()
        super().tearDown()

    def test_prefers_matrix_fields_when_present(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "Paper With Matrix Data", "authors": "A", "year": 2024,
            "abstract": "The abstract, which should be ignored here.", "source": "semantic_scholar",
        })
        set_paper_matrix_fields(self.db, paper, "Interviews", "20 participants", "Mixed results", "Small sample")
        capsule = build_synthesis_capsule(paper)
        self.assertIn("Methodology: Interviews", capsule)
        self.assertNotIn("should be ignored", capsule)

    def test_falls_back_to_abstract_when_no_matrix_data(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "Paper Without Matrix Data", "authors": "A", "year": 2024,
            "abstract": "This is the only thing we have.", "source": "semantic_scholar",
        })
        capsule = build_synthesis_capsule(paper)
        self.assertEqual(capsule, "Abstract: This is the only thing we have.")

    def test_falls_back_to_a_plain_message_when_nothing_is_available(self):
        paper = create_paper_from_search_result(self.db, {
            "title": "Bare Paper", "authors": None, "year": None,
            "abstract": None, "source": "semantic_scholar",
        })
        capsule = build_synthesis_capsule(paper)
        self.assertIn("No abstract, extracted text, or matrix fields", capsule)


class SynthesisTwoPaperGuardTests(DatabaseTestCase):
    """stream_synthesize_papers() is a generator - the 2-paper guard is the very
    first thing it does, before it would ever try to contact OpenAI, so this is
    safe to call directly in a test with no API key configured."""

    def test_zero_papers_yields_an_error_and_nothing_else(self):
        events = list(stream_synthesize_papers("A Project", "A question?", []))
        self.assertEqual(len(events), 1)
        self.assertIn("error", events[0])
        self.assertIn("at least 2", events[0]["error"])

    def test_one_paper_yields_an_error_and_nothing_else(self):
        events = list(stream_synthesize_papers("A Project", "A question?", [
            {"title": "Only One", "authors": "A", "year": 2024, "capsule": "..."},
        ]))
        self.assertEqual(len(events), 1)
        self.assertIn("error", events[0])
