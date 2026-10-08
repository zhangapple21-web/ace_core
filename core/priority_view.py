"""Prioritization view: rank open questions with auditable reasons.

Read-only. This does NOT reorder TaskPool execution; the lifecycle keeps
its own ordering. It answers "why this one first" on paper so the future
scheduler has a receipt format to implement: selected, why, rejected
alternatives, policy version, inputs.
"""

from __future__ import annotations

from typing import Any, Dict, List

POLICY_VERSION = "ace.priority.view.v1"

# Weights are explicit and provisional: they rank, they do not judge.
# Calibrate against review outcomes, never by gut feeling.
WEIGHTS = {
    "value": 0.30,
    "urgency": 0.15,
    "uncertainty": 0.15,
    "learning": 0.15,
    "consequence": 0.15,
    "age": 0.05,
    "cost": -0.05,
}

HARD_EXCLUDE = (
    "terminal_non_convergent",
    "already_archived",
    "duplicate",
    "over_budget",
)


def score(candidate: Dict[str, Any]) -> float:
    """Weighted sum over 0..1 factors. Missing factors count 0, never default."""
    total = 0.0
    for name, weight in WEIGHTS.items():
        try:
            value = float(candidate.get(name, 0.0) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        total += weight * max(0.0, min(1.0, value))
    return round(total, 4)


def rank(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Return an auditable ranking receipt, highest first."""
    eligible = []
    excluded = []
    for candidate in candidates:
        blockers = [
            flag for flag in HARD_EXCLUDE if candidate.get(flag) is True
        ]
        if blockers:
            excluded.append(
                {"id": candidate.get("id"), "blocked_by": blockers}
            )
            continue
        eligible.append(candidate)
    ordered = sorted(
        eligible, key=lambda item: (score(item), str(item.get("id", ""))), reverse=True
    )
    receipt: Dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "weights": dict(WEIGHTS),
        "selected": ordered[0].get("id") if ordered else None,
        "ranking": [
            {"id": item.get("id"), "score": score(item)} for item in ordered
        ],
        "rejected_alternatives": [
            {
                "id": item.get("id"),
                "score": score(item),
                "reason": "lower ranked value under %s" % POLICY_VERSION,
            }
            for item in ordered[1:4]
        ],
        "excluded": excluded,
        "inputs": sorted(
            {key for item in candidates for key in item.keys() if key != "id"}
        ),
    }
    if ordered:
        top = ordered[0]
        receipt["why"] = (
            "highest weighted value under %s; "
            "see ranking and rejected alternatives for the full comparison"
            % POLICY_VERSION
        )
        receipt["why_factors"] = {
            name: round(max(0.0, min(1.0, float(top.get(name, 0.0) or 0.0))), 4)
            for name in WEIGHTS
        }
    return receipt


__all__ = ["POLICY_VERSION", "WEIGHTS", "score", "rank"]
