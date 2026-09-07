"""Fail-closed gate for deciding whether a worker may continue a long turn.

The gate is deliberately small and model/provider agnostic.  It turns the
lesson from long Codex turns into an executable boundary shared by ACE,
Free Zone experiments, and Video Kingdom: before doing more work, prove that
the context is fresh enough, the protocol can carry the next operation, and
the previous operation has a trustworthy receipt.  If any proof is missing,
the caller must record a handoff receipt and start a fresh context instead of
retrying the same question or external action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List


SCHEMA_VERSION = 1
CONTINUE = "CONTINUE"
CLOSE_AND_HANDOFF = "CLOSE_AND_HANDOFF"


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _receipt_is_valid(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return _nonempty(value.get("receipt_id")) and _nonempty(value.get("status"))


def evaluate_continue_gate(
    context: Dict[str, Any] | None,
    protocol: Dict[str, Any] | None,
    evidence: Dict[str, Any] | None,
    *,
    soft_context_ratio: float = 0.80,
    repeated_failure_limit: int = 2,
) -> Dict[str, Any]:
    """Return a truthful, fail-closed decision for the next operation.

    ``CONTINUE`` is only returned when all three proof classes are present.
    Missing or malformed proof is never treated as permission.  The function
    does not invoke a model, submit provider work, or write a receipt.
    """

    context = context if isinstance(context, dict) else {}
    protocol = protocol if isinstance(protocol, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    reasons: List[str] = []

    if context.get("fresh") is not True:
        reasons.append("CONTEXT_NOT_FRESH")
    if not _nonempty(context.get("context_id")):
        reasons.append("CONTEXT_ID_MISSING")
    estimated = context.get("estimated_tokens")
    limit = context.get("context_limit")
    if not isinstance(estimated, (int, float)) or not isinstance(limit, (int, float)) or limit <= 0:
        reasons.append("CONTEXT_BUDGET_UNKNOWN")
    elif estimated / limit >= soft_context_ratio:
        reasons.append("CONTEXT_BUDGET_NEAR_LIMIT")

    repeated = context.get("same_failure_count", 0)
    if not isinstance(repeated, int) or repeated < 0:
        reasons.append("FAILURE_COUNT_INVALID")
    elif repeated >= repeated_failure_limit:
        reasons.append("REPEATED_FAILURE_LIMIT")

    if context.get("prior_attempt_without_receipt") is True:
        reasons.append("PRIOR_ATTEMPT_HAS_NO_RECEIPT")

    if protocol.get("available") is not True:
        reasons.append("PROTOCOL_UNAVAILABLE")
    if not _nonempty(protocol.get("provider")) or not _nonempty(protocol.get("interface")):
        reasons.append("PROTOCOL_IDENTITY_INCOMPLETE")
    if protocol.get("continuation_supported") is not True:
        reasons.append("CONTINUATION_UNVERIFIED")
    if protocol.get("provider_degraded") is True and protocol.get("fallbacks_configured") is not True:
        reasons.append("NO_FALLBACK_ON_DEGRADED_PROVIDER")

    required = evidence.get("required_receipts", [])
    receipts = evidence.get("receipts", [])
    if not isinstance(required, list) or not isinstance(receipts, list):
        reasons.append("EVIDENCE_SHAPE_INVALID")
    else:
        receipt_ids = {item.get("receipt_id") for item in receipts if _receipt_is_valid(item)}
        missing = [item for item in required if item not in receipt_ids]
        if missing and evidence.get("allow_empty_for_new_experiment") is not True:
            reasons.append("REQUIRED_RECEIPT_MISSING")
        if any(not _receipt_is_valid(item) for item in receipts):
            reasons.append("INVALID_RECEIPT_PRESENT")

    status = CONTINUE if not reasons else CLOSE_AND_HANDOFF
    return {
        "contract_version": f"continue_before_work.v{SCHEMA_VERSION}",
        "status": status,
        "reason_codes": reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "next_step": "continue_current_context" if status == CONTINUE else "write_handoff_receipt_and_start_fresh_context",
        "external_action_permitted": status == CONTINUE,
    }


__all__ = ["CONTINUE", "CLOSE_AND_HANDOFF", "evaluate_continue_gate"]
