"""Evidence-aware merge, validation, and interview planning."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .scoring import score_case


ALLOWED_EVIDENCE = {"confirmed", "system_verified", "estimate", "assumption", "unknown"}
PROTECTED_ROOTS = {"case_id", "schema_version", "score", "audit", "approvals"}
ALLOWED_FACT_PATHS = {
    "summary.problem_statement",
    "summary.goal",
    "ownership.process_owner",
    "ownership.requesting_unit",
    "current_state.trigger",
    "current_state.steps",
    "current_state.outcome",
    "current_state.exceptions",
    "value.annual_manual_hours",
    "value.measurement_plan",
    "value.pain_severity_1_to_5",
    "value.error_rework_severity_1_to_5",
    "value.strategic_alignment_1_to_5",
    "value.reuse_potential_1_to_5",
    "systems.primary_systems",
    "systems.available_interfaces",
    "data.highest_classification",
    "data.records_in_scope",
    "controls.human_oversight_1_to_5",
    "controls.decision_reversibility_1_to_5",
    "controls.prohibited_actions",
    "controls.approval_points",
    "controls.audit_requirements",
    "feasibility.rule_based_share_pct",
    "feasibility.digital_input_share_pct",
    "feasibility.access_readiness_1_to_5",
    "target_state.user_journey",
    "target_state.automation_boundary",
    "target_state.fallback_path",
    "ui.channels",
    "success_metrics.primary_metric",
    "success_metrics.baseline",
    "success_metrics.target",
    "delivery.dependencies",
    "delivery.pilot_scope",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_question_bank(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else _repo_root() / "config" / "question_bank.json"
    return json.loads(target.read_text(encoding="utf-8"))


def create_case(case_id: str) -> dict[str, Any]:
    """Create an empty canonical case with every controlled fact marked unknown."""
    record: dict[str, Any] = {
        "case_id": case_id,
        "schema_version": "1.0",
        "score": {},
        "audit": {"prompt_version": "1.0", "question_bank_version": "1.0"},
        "approvals": {},
    }
    for path in sorted(ALLOWED_FACT_PATHS):
        section, field = path.split(".", 1)
        record.setdefault(section, {})[field] = {
            "value": None,
            "evidence": "unknown",
            "source_ref": "",
            "notes": "",
        }
    record["score"] = score_case(record).to_dict()
    return record


def _get(record: dict[str, Any], path: str) -> Any:
    node: Any = record
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node.get("value") if isinstance(node, dict) and "value" in node else node


def _has_evidence_value(value: Any) -> bool:
    if not isinstance(value, dict) or "value" not in value:
        return False
    return value.get("evidence") in ALLOWED_EVIDENCE and value.get("evidence") != "unknown" and value.get("value") not in (None, "", [])


def _merge(target: dict[str, Any], patch: dict[str, Any], path: str, rejected: list[str]) -> None:
    for key, incoming in patch.items():
        current_path = f"{path}.{key}" if path else key
        if not path and key in PROTECTED_ROOTS:
            rejected.append(f"{current_path}: model cannot update protected fields")
            continue
        if isinstance(incoming, dict) and "value" in incoming:
            if current_path not in ALLOWED_FACT_PATHS:
                rejected.append(f"{current_path}: field is not in the controlled schema")
                continue
            evidence = incoming.get("evidence", "unknown")
            if evidence not in ALLOWED_EVIDENCE:
                rejected.append(f"{current_path}: invalid evidence label")
                continue
            if evidence in {"confirmed", "system_verified"} and not incoming.get("source_ref"):
                rejected.append(f"{current_path}: confirmed facts require source_ref")
                continue
            clean = {
                "value": incoming.get("value"),
                "evidence": evidence,
                "source_ref": incoming.get("source_ref", ""),
                "notes": incoming.get("notes", ""),
            }
            target[key] = clean
        elif isinstance(incoming, dict):
            if not any(allowed.startswith(f"{current_path}.") for allowed in ALLOWED_FACT_PATHS):
                rejected.append(f"{current_path}: section is not in the controlled schema")
                continue
            existing = target.get(key)
            if not isinstance(existing, dict) or "value" in existing:
                existing = {}
                target[key] = existing
            _merge(existing, incoming, current_path, rejected)
        else:
            rejected.append(f"{current_path}: every model-proposed fact must use the evidence wrapper")


def merge_candidate_patch(current: dict[str, Any], patch: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge a model-proposed patch while enforcing provenance and protected fields."""
    result = copy.deepcopy(current)
    rejected: list[str] = []
    _merge(result, patch, "", rejected)
    result["score"] = score_case(result).to_dict()
    return result, rejected


def next_questions(record: dict[str, Any], limit: int = 3, bank: dict[str, Any] | None = None) -> list[dict[str, str]]:
    bank = bank or load_question_bank()
    selected: list[dict[str, str]] = []
    for stage in bank["stages"]:
        missing = [path for path in stage["required_paths"] if _get(record, path) in (None, "", [])]
        if not missing:
            continue
        by_path = {item["path"]: item for item in stage["questions"]}
        for path in missing:
            if path in by_path:
                selected.append(
                    {
                        "stage": stage["id"],
                        "path": path,
                        "question": by_path[path]["question"],
                        "why": by_path[path]["why"],
                    }
                )
                if len(selected) >= limit:
                    return selected
        return selected
    return selected


def evaluate_case(record: dict[str, Any]) -> dict[str, Any]:
    questions = next_questions(record)
    score = score_case(record).to_dict()
    return {
        "status": "ready_for_review" if not questions and not score["blockers"] else "discovery_in_progress",
        "next_questions": questions,
        "score": score,
        "can_generate_draft": not score["blockers"],
        "can_approve_solution": False,
    }
