"""Small, replayable observation/action/feedback units for ACE learning.

This contract is descriptive evidence only.  It has no model, TaskPool,
network, Advisor, Risk, broker, or outbound side effects.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

CONTRACT_VERSION = "ace.micro_observation.v1"
REQUIRED_KEYS = frozenset({
    "contract_version", "observation", "intent", "constraints", "action",
    "result", "feedback", "next_question", "evidence_refs",
    "production_integration",
})
FORBIDDEN_KEYS = frozenset({"advisor", "broker", "order", "recommendation", "telegram", "target_price"})


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reject_forbidden(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                raise ValueError(f"micro_observation contains forbidden field: {key}")
            _reject_forbidden(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden(item)


def validate_micro_observation(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and copy one atomic learning unit."""
    if not isinstance(value, Mapping) or set(value) != REQUIRED_KEYS:
        raise ValueError("micro_observation has missing or unknown fields")
    _reject_forbidden(value)
    for key in ("observation", "intent", "action", "result", "feedback", "next_question"):
        if not _non_empty(value.get(key)):
            raise ValueError(f"micro_observation {key} must be non-empty")
    if not isinstance(value.get("constraints"), list) or any(not _non_empty(item) for item in value["constraints"]):
        raise ValueError("micro_observation constraints must be a list of non-empty strings")
    refs = value.get("evidence_refs")
    if not isinstance(refs, list) or not refs or any(not _non_empty(item) for item in refs):
        raise ValueError("micro_observation evidence_refs must be a non-empty string list")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported micro_observation contract_version")
    if value.get("production_integration") is not False:
        raise ValueError("micro_observation production_integration must be false")
    return json.loads(json.dumps(dict(value), ensure_ascii=False))


def build_micro_observation(
    *, observation: str, intent: str, constraints: list[str], action: str,
    result: str, feedback: str, next_question: str, evidence_refs: list[str],
) -> dict[str, Any]:
    value = {
        "contract_version": CONTRACT_VERSION,
        "observation": observation,
        "intent": intent,
        "constraints": list(constraints),
        "action": action,
        "result": result,
        "feedback": feedback,
        "next_question": next_question,
        "evidence_refs": list(evidence_refs),
        "production_integration": False,
    }
    return validate_micro_observation(value)
