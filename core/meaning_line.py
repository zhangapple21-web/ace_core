"""Pure validation for bounded, explicit-input meaning candidates.

This module intentionally does not store a user profile, inspect a device, or
feed ACE Runtime.  It only decides whether caller-supplied, minimized material
may remain a ``FREE_ZONE_ONLY`` shadow candidate for later human review.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.meaning_line.v1"
ALLOWED_SOURCE_SCOPES = {"EXPLICIT_USER_INPUT", "AUTHORIZED_PROJECT_CONTEXT"}
ALLOWED_CLAIM_CLASSES = {"FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN"}
FORBIDDEN_FIELDS = {
    "raw_chat", "screen", "browser", "email", "clipboard", "persona",
    "emotion", "relationship", "financial_profile", "task_id", "worker",
    "model", "dispatch", "action", "message", "file_mutation",
}


def validate_meaning_line_batch(
    items: Sequence[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any],
    existing_candidates: Sequence[Mapping[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    """Validate an in-memory batch without persistence or side effects."""
    max_items = policy.get("max_items")
    if not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1:
        return _rejected("REJECTED_POLICY_MAX_ITEMS")
    if len(items) > max_items:
        return _rejected("REJECTED_BATCH_LIMIT")

    existing_keys = {
        str(candidate.get("semantic_key", ""))
        for candidate in existing_candidates
        if isinstance(candidate, Mapping)
    }
    seen_keys: set[str] = set()
    accepted: list[dict[str, Any]] = []
    for item in items:
        verdict = _validate_item(item, now=now, existing_keys=existing_keys | seen_keys)
        if verdict["verdict"] != "VALID_SHADOW_BATCH":
            return verdict
        shadow = verdict["shadow_batch"][0]
        seen_keys.add(shadow["semantic_key"])
        accepted.append(shadow)

    return {
        "contract_version": CONTRACT_VERSION,
        "verdict": "VALID_SHADOW_BATCH",
        "reason_code": "VALID",
        "shadow_batch": accepted,
        "side_effects": _no_side_effects(),
    }


def _validate_item(
    item: Mapping[str, Any], *, now: datetime, existing_keys: set[str]) -> dict[str, Any]:
    if not isinstance(item, Mapping):
        return _rejected("REJECTED_ITEM_NOT_MAPPING")
    if _contains_forbidden_field(item):
        return _rejected("REJECTED_FORBIDDEN_FIELD")
    required = {
        "contract_version", "source_scope", "source_refs", "observed_at", "expires_at",
        "claim_class", "claim_kind", "claim", "candidate_envelope",
    }
    if not required.issubset(item):
        return _rejected("REJECTED_MISSING_REQUIRED_FIELD")
    if item.get("contract_version") != CONTRACT_VERSION:
        return _rejected("REJECTED_CONTRACT_VERSION")
    if item.get("source_scope") not in ALLOWED_SOURCE_SCOPES:
        return _rejected("REJECTED_SOURCE_SCOPE")
    if item.get("claim_class") not in ALLOWED_CLAIM_CLASSES:
        return _rejected("REJECTED_CLAIM_CLASS")
    if item.get("claim_kind") not in {"DIRECT_OBSERVATION", "OWNER_INTERPRETATION"}:
        return _rejected("REJECTED_CLAIM_KIND")
    if item.get("claim_kind") == "OWNER_INTERPRETATION" and item.get("claim_class") != "HYPOTHESIS":
        return _rejected("REJECTED_OWNER_INTERPRETATION_NOT_HYPOTHESIS")
    if not isinstance(item.get("claim"), str) or not item["claim"].strip():
        return _rejected("REJECTED_CLAIM_EMPTY")
    if not _valid_source_refs(item.get("source_refs")):
        return _rejected("REJECTED_SOURCE_REFS")

    observed_at = _parse_time(item.get("observed_at"))
    expires_at = _parse_time(item.get("expires_at"))
    if observed_at is None or expires_at is None or observed_at > expires_at:
        return _rejected("REJECTED_INVALID_TIME_RANGE")
    if expires_at <= now:
        return _rejected("REJECTED_SOURCE_EXPIRED")

    envelope = item.get("candidate_envelope")
    if not isinstance(envelope, Mapping):
        return _rejected("REJECTED_ENVELOPE_NOT_MAPPING")
    semantic_key = envelope.get("semantic_key")
    if not isinstance(semantic_key, str) or not semantic_key.strip():
        return _rejected("REJECTED_SEMANTIC_KEY")
    if semantic_key in existing_keys:
        return _rejected("REJECTED_DUPLICATE_SEMANTIC_KEY")
    if not isinstance(envelope.get("candidate_snapshot_hash"), str) or not envelope["candidate_snapshot_hash"].strip():
        return _rejected("REJECTED_SNAPSHOT_HASH")
    if not isinstance(envelope.get("selection_reason"), str) or not envelope["selection_reason"].strip():
        return _rejected("REJECTED_SELECTION_REASON")
    if envelope.get("sandbox_scope") != "FREE_ZONE_ONLY":
        return _rejected("REJECTED_SANDBOX_SCOPE")
    if envelope.get("review_status") != "NEEDS_HUMAN_CONFIRMATION":
        return _rejected("REJECTED_REVIEW_STATUS")

    return {
        "contract_version": CONTRACT_VERSION,
        "verdict": "VALID_SHADOW_BATCH",
        "reason_code": "VALID",
        "shadow_batch": [{
            "semantic_key": semantic_key,
            "claim_class": item["claim_class"],
            "claim_kind": item["claim_kind"],
            "claim": item["claim"].strip(),
            "source_scope": item["source_scope"],
            "source_refs": list(item["source_refs"]),
            "observed_at": item["observed_at"],
            "expires_at": item["expires_at"],
            "counterexample_ref": item.get("counterexample_ref"),
            "candidate_snapshot_hash": envelope["candidate_snapshot_hash"],
            "selection_reason": envelope["selection_reason"],
            "sandbox_scope": "FREE_ZONE_ONLY",
            "review_status": "NEEDS_HUMAN_CONFIRMATION",
        }],
        "side_effects": _no_side_effects(),
    }


def _contains_forbidden_field(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(key) in FORBIDDEN_FIELDS or _contains_forbidden_field(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_contains_forbidden_field(child) for child in value)
    return False


def _valid_source_refs(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(ref, str) and ref.strip() for ref in value)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _rejected(reason_code: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "verdict": "REJECTED",
        "reason_code": reason_code,
        "shadow_batch": [],
        "side_effects": _no_side_effects(),
    }


def _no_side_effects() -> dict[str, bool]:
    return {
        "persistent_write": False,
        "task_created": False,
        "model_called": False,
        "daemon_called": False,
        "external_action": False,
    }
