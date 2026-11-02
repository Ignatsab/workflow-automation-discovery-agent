"""Deterministic and explainable automation-opportunity scoring."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


EVIDENCE_WEIGHTS = {
    "system_verified": 1.0,
    "confirmed": 1.0,
    "estimate": 0.6,
    "assumption": 0.25,
    "unknown": 0.0,
}


@dataclass(frozen=True)
class ScoreResult:
    raw_score: float
    confidence: float
    adjusted_score: float
    recommendation: str
    dimensions: dict[str, float]
    blockers: list[str]
    score_version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(record: dict[str, Any], path: str, default: Any = None) -> Any:
    node: Any = record
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    if isinstance(node, dict) and "value" in node:
        return node.get("value", default)
    return node


def _evidence(record: dict[str, Any], path: str) -> str:
    node: Any = record
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            return "unknown"
        node = node[key]
    return node.get("evidence", "unknown") if isinstance(node, dict) else "unknown"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _linear(value: float, low: float, high: float, points: float) -> float:
    if high <= low:
        return 0.0
    return _clamp((value - low) / (high - low), 0.0, 1.0) * points


def score_case(record: dict[str, Any]) -> ScoreResult:
    """Return a transparent 0-100 score with an evidence-confidence adjustment.

    The weights are intentionally fixed in code. A model may propose input values but
    cannot change weights, thresholds, blockers, or the final result.
    """

    hours = float(_value(record, "value.annual_manual_hours", 0) or 0)
    pain = float(_value(record, "value.pain_severity_1_to_5", 0) or 0)
    error = float(_value(record, "value.error_rework_severity_1_to_5", 0) or 0)
    strategic = float(_value(record, "value.strategic_alignment_1_to_5", 0) or 0)
    reuse = float(_value(record, "value.reuse_potential_1_to_5", 0) or 0)
    rule_share = float(_value(record, "feasibility.rule_based_share_pct", 0) or 0)
    digital_share = float(_value(record, "feasibility.digital_input_share_pct", 0) or 0)
    access = float(_value(record, "feasibility.access_readiness_1_to_5", 0) or 0)
    reversibility = float(_value(record, "controls.decision_reversibility_1_to_5", 0) or 0)
    oversight = float(_value(record, "controls.human_oversight_1_to_5", 0) or 0)

    dimensions = {
        "capacity_and_pain": round(_linear(hours, 0, 5000, 20) + _linear(pain, 1, 5, 5), 2),
        "quality_and_risk_reduction": round(_linear(error, 1, 5, 10), 2),
        "feasibility": round(
            _linear(rule_share, 0, 100, 8)
            + _linear(digital_share, 0, 100, 6)
            + _linear(access, 1, 5, 6),
            2,
        ),
        "control_viability": round(
            _linear(reversibility, 1, 5, 5) + _linear(oversight, 1, 5, 5), 2
        ),
        "strategic_alignment": round(_linear(strategic, 1, 5, 10), 2),
        "reuse_potential": round(_linear(reuse, 1, 5, 5), 2),
    }

    readiness_fields = [
        "ownership.process_owner",
        "current_state.trigger",
        "current_state.outcome",
        "value.annual_manual_hours",
        "systems.primary_systems",
        "data.highest_classification",
        "controls.human_oversight_1_to_5",
        "success_metrics.primary_metric",
    ]
    answered = sum(_evidence(record, path) != "unknown" for path in readiness_fields)
    dimensions["discovery_readiness"] = round(answered / len(readiness_fields) * 20, 2)

    raw = round(sum(dimensions.values()), 2)
    confidence_fields = [
        "value.annual_manual_hours",
        "value.pain_severity_1_to_5",
        "value.error_rework_severity_1_to_5",
        "value.strategic_alignment_1_to_5",
        "value.reuse_potential_1_to_5",
        "feasibility.rule_based_share_pct",
        "feasibility.digital_input_share_pct",
        "feasibility.access_readiness_1_to_5",
        "controls.decision_reversibility_1_to_5",
        "controls.human_oversight_1_to_5",
    ]
    confidence = round(
        sum(EVIDENCE_WEIGHTS.get(_evidence(record, path), 0) for path in confidence_fields)
        / len(confidence_fields),
        3,
    )
    adjusted = round(raw * (0.55 + 0.45 * confidence), 2)

    blockers: list[str] = []
    if not _value(record, "ownership.process_owner"):
        blockers.append("Process owner is not identified")
    if not _value(record, "current_state.steps"):
        blockers.append("Current-state steps are not confirmed")
    if not hours and not _value(record, "value.measurement_plan"):
        blockers.append("No volume or effort baseline and no measurement plan")
    if not _value(record, "systems.primary_systems"):
        blockers.append("Systems in scope are not identified")
    if not _value(record, "data.highest_classification"):
        blockers.append("Data classification is unknown")
    if not _value(record, "controls.prohibited_actions"):
        blockers.append("Prohibited autonomous actions are not defined")

    if blockers:
        recommendation = "Discovery incomplete"
    elif adjusted >= 80 and confidence >= 0.8:
        recommendation = "Fast track for feasibility and control review"
    elif adjusted >= 65:
        recommendation = "Prioritize discovery and prototype"
    elif adjusted >= 45:
        recommendation = "Keep in backlog pending evidence or simplification"
    else:
        recommendation = "Do not prioritize without a stronger case"

    return ScoreResult(raw, confidence, adjusted, recommendation, dimensions, blockers)

