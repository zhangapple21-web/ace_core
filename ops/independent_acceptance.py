"""Independent, read-only evidence checks for the ACE start boundary.

The checker reads durable JSON files directly and deliberately does not import
TaskPool or execution-discipline helpers.  A separate process can therefore
replay the receipt without trusting the code that performed the start.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_task_file(path: Path) -> Dict[str, Any]:
    """Return facts from one persisted task record without repairing it."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"valid": False, "path": str(path), "error": f"unreadable:{exc}"}
    if not isinstance(payload, dict):
        return {"valid": False, "path": str(path), "error": "task_record_not_object"}
    outputs = payload.get("outputs")
    envelope = outputs.get("execution_discipline") if isinstance(outputs, dict) else None
    envelope_valid = (
        isinstance(envelope, dict)
        and envelope.get("protocol") == "ACE-EXECUTION-DISCIPLINE-1.1"
        and envelope.get("start_protocol") == "ACE-START-PROTOCOL-2.0"
        and envelope.get("complexity") in {"simple", "medium", "complex"}
        and isinstance(envelope.get("pipeline"), dict)
        and isinstance(envelope.get("events"), list)
    )
    return {
        "valid": True,
        "path": str(path),
        "sha256": _sha256(path),
        "task_id": payload.get("task_id", ""),
        "status": payload.get("status", ""),
        "lease_owner": payload.get("lease_owner", ""),
        "claim_id": payload.get("claim_id", ""),
        "fencing_token": payload.get("fencing_token", 0),
        "execution_discipline_present": isinstance(
            envelope,
            dict,
        ),
        "execution_discipline_valid": envelope_valid,
        "execution_discipline_protocol": envelope.get("protocol") if isinstance(envelope, dict) else None,
        "execution_discipline_start_protocol": envelope.get("start_protocol") if isinstance(envelope, dict) else None,
    }


def build_acceptance_receipt(
    *,
    task_path: Path,
    before: Dict[str, Any],
    after: Dict[str, Any],
    protocol_receipt: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a verdict without changing runtime state."""

    errors = []
    if not before.get("valid") or not after.get("valid"):
        errors.append("task_record_unreadable")
    if before.get("task_id") != after.get("task_id"):
        errors.append("task_identity_changed")
    if protocol_receipt.get("valid") is not True:
        errors.append("protocol_receipt_not_valid")
    if protocol_receipt.get("errors"):
        errors.append("protocol_receipt_contains_errors")
    # The receipt is evidence supplied by another process, not authority.  It
    # must be bound to the exact task being inspected; otherwise a forged
    # valid receipt for a different task could bless an unrelated record.
    if protocol_receipt.get("task_id") != after.get("task_id"):
        errors.append("protocol_receipt_task_mismatch")
    if protocol_receipt.get("protocol") != after.get("execution_discipline_protocol"):
        errors.append("protocol_receipt_protocol_mismatch")
    if protocol_receipt.get("start_protocol") != after.get("execution_discipline_start_protocol"):
        errors.append("protocol_receipt_start_protocol_mismatch")
    # Re-check the persisted record itself.  Do not trust the mutating
    # process's `valid` bit as proof that an envelope exists.
    if after.get("execution_discipline_present") is not True:
        errors.append("missing_execution_discipline_envelope")
    if after.get("execution_discipline_valid") is not True:
        errors.append("invalid_execution_discipline_envelope")
    if after.get("status") != "active":
        errors.append("task_not_active_after_start")
    if not after.get("lease_owner") or not after.get("claim_id") or not after.get("fencing_token"):
        errors.append("missing_owner_claim_or_fencing")
    return {
        "receipt_version": "ACE-INDEPENDENT-ACCEPTANCE-1.0",
        "verdict": "PASS" if not errors else "FAIL",
        "task_path": str(task_path),
        "before": before,
        "after": after,
        "protocol_receipt": protocol_receipt,
        "errors": errors,
        "authority": "ACE_TASKPOOL",
        "runtime_mutation_by_checker": False,
    }


def main(argv=None) -> int:
    """Validate a start receipt from files produced by a separate process."""

    import argparse

    parser = argparse.ArgumentParser(description="Read-only ACE start acceptance")
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    args = parser.parse_args(argv)
    before = json.loads(args.before.read_text(encoding="utf-8"))
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    after = inspect_task_file(args.task)
    receipt = build_acceptance_receipt(
        task_path=args.task,
        before=before,
        after=after,
        protocol_receipt=protocol,
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

