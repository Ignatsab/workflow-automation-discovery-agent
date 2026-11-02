"""Paste this file into a Langflow custom component after installing this package.

The component intentionally contains no model call and no persistence. It accepts a
candidate patch, rejects unsupported facts, calculates the score, and selects the
next questions. Persist `updated_case` in an approved case store outside the model.
"""

import json

from langflow.custom import Component
from langflow.io import MultilineInput, Output
from langflow.schema import Data

from use_case_agent.engine import evaluate_case, merge_candidate_patch


class IntakeControlGate(Component):
    display_name = "Intake Control Gate"
    description = "Validates evidence, protects controlled fields, scores the case, and plans follow-up questions."
    icon = "ShieldCheck"
    name = "IntakeControlGate"

    inputs = [
        MultilineInput(
            name="current_case_json",
            display_name="Current Case JSON",
            info="Canonical case read from the approved case store.",
            required=True,
        ),
        MultilineInput(
            name="candidate_patch_json",
            display_name="Candidate Patch JSON",
            info="Evidence-wrapped patch produced by Structured Output.",
            required=True,
        ),
    ]

    outputs = [
        Output(name="updated_case", display_name="Updated Case", method="build_updated_case"),
        Output(name="control_result", display_name="Control Result", method="build_control_result"),
    ]

    def _run(self):
        current = json.loads(self.current_case_json)
        patch = json.loads(self.candidate_patch_json)
        updated, rejected = merge_candidate_patch(current, patch)
        result = evaluate_case(updated)
        result["rejected_updates"] = rejected
        return updated, result

    def build_updated_case(self) -> Data:
        updated, _ = self._run()
        self.status = f"Case {updated.get('case_id', 'unknown')} validated"
        return Data(data=updated)

    def build_control_result(self) -> Data:
        _, result = self._run()
        return Data(data=result)

