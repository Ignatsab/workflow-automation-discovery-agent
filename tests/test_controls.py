import json
import unittest
from pathlib import Path

from use_case_agent.engine import create_case, merge_candidate_patch, next_questions
from use_case_agent.scoring import score_case


ROOT = Path(__file__).resolve().parents[1]


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.case = json.loads((ROOT / "examples" / "sample_case.json").read_text())

    def test_model_cannot_overwrite_score(self):
        updated, rejected = merge_candidate_patch(self.case, {"score": {"adjusted_score": 100}})
        self.assertTrue(any("protected" in item for item in rejected))
        self.assertNotEqual(updated["score"]["adjusted_score"], 100)

    def test_confirmed_fact_requires_source(self):
        patch = {"summary": {"goal": {"value": "Invented", "evidence": "confirmed", "source_ref": "", "notes": ""}}}
        updated, rejected = merge_candidate_patch(self.case, patch)
        self.assertTrue(rejected)
        self.assertNotEqual(updated["summary"]["goal"]["value"], "Invented")

    def test_unknown_field_is_rejected(self):
        patch = {"financial_advice": {"recommendation": {"value": "Buy", "evidence": "assumption", "source_ref": "", "notes": ""}}}
        updated, rejected = merge_candidate_patch(self.case, patch)
        self.assertTrue(any("controlled schema" in item for item in rejected))
        self.assertNotIn("financial_advice", updated)

    def test_new_case_starts_at_first_interview_stage(self):
        record = create_case("TEST-001")
        questions = next_questions(record)
        self.assertEqual(questions[0]["stage"], "purpose_and_ownership")
        self.assertLessEqual(len(questions), 3)

    def test_unknown_evidence_reduces_adjusted_score(self):
        baseline = score_case(self.case)
        for section, field in (("value", "pain_severity_1_to_5"), ("feasibility", "rule_based_share_pct"), ("controls", "human_oversight_1_to_5")):
            self.case[section][field]["evidence"] = "unknown"
        lower = score_case(self.case)
        self.assertLess(lower.confidence, baseline.confidence)
        self.assertLess(lower.adjusted_score, baseline.adjusted_score)


if __name__ == "__main__":
    unittest.main()
