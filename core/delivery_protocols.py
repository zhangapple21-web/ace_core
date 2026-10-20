"""Minimal Work Contract, Evidence Packet and Release Receipt protocols.

These records are deliberately small projections around the existing TaskPool
task envelope.  They are not a second queue, scheduler, or authority.  The
TaskPool owns lifecycle state; Validator and Guardian only consume and record
protocol checks at their existing lifecycle boundaries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .mirror_constitution import (
    build_responsibility_packet,
    validate_responsibility_packet,
)


WORK_CONTRACT_PROTOCOL = "ACE-WORK-CONTRACT-1.0"
EVIDENCE_PACKET_PROTOCOL = "ACE-EVIDENCE-PACKET-1.0"
RELEASE_RECEIPT_PROTOCOL = "ACE-RELEASE-RECEIPT-1.0"

RELEASE_STATUSES = {"NOT_APPLICABLE", "BUILT", "DEPLOYED", "VERIFIED", "BLOCKED"}
WORK_STATUSES = {"CANDIDATE", "ADMITTED", "IN_PROGRESS", "VERIFIED", "RELEASED", "ACCEPTED", "SEDIMENTED"}
COMPLETENESS_STATUSES = {"COMPLETE", "COMPLETE_WITH_WARNINGS", "INCOMPLETE_GAPS"}
PROTOCOL_TRIGGER_TAGS = {
    "production",
    "production_gate",
    "external_delivery",
    "delivery",
    "release",
    "long_term_rule",
    "axiom",
    "constraint",
    "protocol_gate",
}


def _now() -> str:
    return datetime.now().isoformat()


def _strings(values: Any) -> List[str]:
    if not isinstance(values, (list, tuple)):
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _error_result(errors: Iterable[str], **extra: Any) -> Dict[str, Any]:
    errors = list(dict.fromkeys(str(error) for error in errors if error))
    return {"valid": not errors, "errors": errors, **extra}


def build_work_contract(
    *,
    task_id: str,
    title: str,
    hypothesis: str = "",
    admission: Optional[Mapping[str, Any]] = None,
    purpose: str = "internal_production",
    delivery_required: bool = False,
) -> Dict[str, Any]:
    admission = admission if isinstance(admission, Mapping) else {}
    evidence = admission.get("evidence", [])
    evidence_refs = []
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, Mapping):
                ref = item.get("source_ref") or item.get("source") or item.get("observation_id")
                if ref:
                    evidence_refs.append(str(ref))
    objective = str(admission.get("expected_result") or hypothesis or title).strip()
    verification = str(
        admission.get("verification_method")
        or "Existing TaskPool → Validator → Guardian lifecycle completes or records an evidence gap."
    ).strip()
    return {
        "protocol": WORK_CONTRACT_PROTOCOL,
        "work_id": str(task_id),
        "purpose": str(purpose or "internal_production"),
        "delivery_required": bool(delivery_required),
        "objective": objective,
        "scope": [str(title).strip()],
        "non_goals": [
            "Do not infer production success from a proposal, report, or self-attestation.",
            "Do not create a second scheduler, queue, or runtime.",
        ],
        "acceptance_criteria": [
            {
                "id": "governed_lifecycle",
                "description": verification,
                "evidence_refs": evidence_refs,
            }
        ],
        "constraints": _strings([admission.get("risk")]),
        "rollback": "Preserve the task in its governed state and record FAILED/UNKNOWN; do not replay successful external actions.",
        "status": "CANDIDATE",
        "created_at": _now(),
        "origin": "taskpool_default",
    }


def validate_work_contract(contract: Any, task_id: Optional[str] = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(contract, Mapping):
        return _error_result(["work_contract_missing"], protocol=None)
    if contract.get("protocol") != WORK_CONTRACT_PROTOCOL:
        errors.append("work_contract_protocol_mismatch")
    if not str(contract.get("work_id", "")).strip():
        errors.append("work_contract_work_id_missing")
    if task_id and str(contract.get("work_id")) != str(task_id):
        errors.append("work_contract_work_id_mismatch")
    if not str(contract.get("purpose", "")).strip():
        errors.append("work_contract_purpose_missing")
    if not str(contract.get("objective", "")).strip():
        errors.append("work_contract_objective_missing")
    criteria = contract.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append("work_contract_acceptance_missing")
    else:
        for index, criterion in enumerate(criteria):
            if not isinstance(criterion, Mapping) or not str(criterion.get("description", "")).strip():
                errors.append(f"work_contract_acceptance_{index}_invalid")
    if contract.get("status") not in WORK_STATUSES:
        errors.append("work_contract_status_invalid")
    if not isinstance(contract.get("delivery_required", False), bool):
        errors.append("work_contract_delivery_required_invalid")
    return _error_result(errors, protocol=contract.get("protocol"))


def build_evidence_packet(task: Any) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    seen = set()
    for index, raw in enumerate(getattr(task, "evidence", []) or []):
        if isinstance(raw, Mapping):
            content = str(raw.get("content") or raw.get("detail") or "").strip()
            source = str(raw.get("source") or raw.get("source_ref") or "").strip()
            evidence_type = str(raw.get("type") or "task_evidence")
        else:
            content = str(raw).strip()
            source = ""
            evidence_type = "task_evidence"
        if not content or not source:
            continue
        key = (source, content)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "id": f"ev-{index + 1:03d}",
                "source": source,
                "independent_group": source,
                "type": evidence_type,
                "content": content[:4000],
            }
        )
    completeness = "COMPLETE" if items else "INCOMPLETE_GAPS"
    return {
        "protocol": EVIDENCE_PACKET_PROTOCOL,
        "work_id": str(getattr(task, "task_id", "")),
        "collected_at": _now(),
        "items": items,
        "independent_groups": sorted({item["independent_group"] for item in items}),
        "completeness": completeness,
        "status": "PASS" if items else "UNKNOWN",
        "gaps": [] if items else ["No source-backed evidence was recorded."],
        "origin": "task_evidence_projection",
    }


def validate_evidence_packet(packet: Any, task_id: Optional[str] = None) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(packet, Mapping):
        return _error_result(["evidence_packet_missing"], protocol=None)
    if packet.get("protocol") != EVIDENCE_PACKET_PROTOCOL:
        errors.append("evidence_packet_protocol_mismatch")
    if not str(packet.get("work_id", "")).strip():
        errors.append("evidence_packet_work_id_missing")
    if task_id and str(packet.get("work_id")) != str(task_id):
        errors.append("evidence_packet_work_id_mismatch")
    items = packet.get("items")
    if not isinstance(items, list):
        errors.append("evidence_packet_items_invalid")
    else:
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                errors.append(f"evidence_packet_item_{index}_invalid")
                continue
            if not str(item.get("source", "")).strip() or not str(item.get("content", "")).strip():
                errors.append(f"evidence_packet_item_{index}_incomplete")
    if packet.get("completeness") not in COMPLETENESS_STATUSES:
        errors.append("evidence_packet_completeness_invalid")
    if packet.get("status") not in {"PASS", "FAIL", "UNKNOWN"}:
        errors.append("evidence_packet_status_invalid")
    return _error_result(errors, protocol=packet.get("protocol"), item_count=len(items) if isinstance(items, list) else 0)


def build_release_receipt(task_id: str) -> Dict[str, Any]:
    return {
        "protocol": RELEASE_RECEIPT_PROTOCOL,
        "work_id": str(task_id),
        "status": "NOT_APPLICABLE",
        "reason": "No deployable artifact or external delivery was declared for this task.",
        "artifact": {},
        "entrypoint": "",
        "smoke_checks": [],
        "rollback": {"ready": False, "method": ""},
        "verified_at": None,
        "origin": "taskpool_default",
    }


def validate_release_receipt(
    receipt: Any,
    task_id: Optional[str] = None,
    *,
    require_verified: bool = False,
) -> Dict[str, Any]:
    errors: List[str] = []
    if not isinstance(receipt, Mapping):
        return _error_result(["release_receipt_missing"], protocol=None)
    if receipt.get("protocol") != RELEASE_RECEIPT_PROTOCOL:
        errors.append("release_receipt_protocol_mismatch")
    if not str(receipt.get("work_id", "")).strip():
        errors.append("release_receipt_work_id_missing")
    if task_id and str(receipt.get("work_id")) != str(task_id):
        errors.append("release_receipt_work_id_mismatch")
    status = receipt.get("status")
    if status not in RELEASE_STATUSES:
        errors.append("release_receipt_status_invalid")
    if status == "NOT_APPLICABLE" and not str(receipt.get("reason", "")).strip():
        errors.append("release_receipt_reason_missing")
    if status in {"BUILT", "DEPLOYED", "VERIFIED"}:
        artifact = receipt.get("artifact")
        if not isinstance(artifact, Mapping) or not str(artifact.get("sha256", "")).strip():
            errors.append("release_receipt_artifact_hash_missing")
    if status in {"DEPLOYED", "VERIFIED"} and not str(receipt.get("entrypoint", "")).strip():
        errors.append("release_receipt_entrypoint_missing")
    if status == "VERIFIED":
        if not isinstance(receipt.get("smoke_checks"), list) or not receipt.get("smoke_checks"):
            errors.append("release_receipt_smoke_checks_missing")
        rollback = receipt.get("rollback")
        if not isinstance(rollback, Mapping) or rollback.get("ready") is not True or not str(rollback.get("method", "")).strip():
            errors.append("release_receipt_rollback_not_ready")
        if not str(receipt.get("verified_at", "")).strip():
            errors.append("release_receipt_verified_at_missing")
    if require_verified and status != "VERIFIED":
        errors.append("release_receipt_delivery_not_verified")
    return _error_result(errors, protocol=receipt.get("protocol"), status=status)


def protocol_scope(task: Any) -> Dict[str, Any]:
    """Return whether the key-node gate is active for this task.

    Ordinary observation, Free Zone and exploratory tasks remain outside the
    protocols unless a caller explicitly opts them in.  A Guardian promotion
    candidate can opt in just-in-time with ``protocols_required=True``.
    """

    outputs = getattr(task, "outputs", None)
    outputs = outputs if isinstance(outputs, dict) else {}
    tags = {str(tag).strip().lower() for tag in (getattr(task, "tags", []) or [])}
    explicit = any(name in outputs for name in ("work_contract", "evidence_packet", "release_receipt"))
    required = outputs.get("protocols_required") is True or explicit or bool(tags & PROTOCOL_TRIGGER_TAGS)
    purpose = str(outputs.get("protocol_purpose", "")).strip()
    if not purpose:
        if "external_delivery" in tags or "delivery" in tags or "release" in tags:
            purpose = "external_delivery"
        elif "long_term_rule" in tags or "axiom" in tags or "constraint" in tags:
            purpose = "long_term_rule"
        else:
            purpose = "internal_production"
    delivery_required = outputs.get("delivery_required") is True or purpose == "external_delivery"
    return {
        "required": required,
        "purpose": purpose,
        "delivery_required": delivery_required,
        "trigger": "explicit" if explicit or outputs.get("protocols_required") is True else (sorted(tags & PROTOCOL_TRIGGER_TAGS) or None),
    }


def ensure_task_protocols(task: Any, *, refresh_evidence: bool = False, force: bool = False) -> Dict[str, Any]:
    """Backfill missing defaults and return validation results.

    Existing explicit records are never silently replaced.  The projected
    evidence packet is refreshed from Task.evidence because Researcher adds
    evidence after TaskPool creation.
    """

    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        outputs = {}
        task.outputs = outputs
    scope = protocol_scope(task)
    if not scope["required"] and not force:
        return {"active": False, "scope": scope, "checks": {}}
    outputs["protocols_required"] = True
    outputs.setdefault("protocol_scope", scope)
    if "work_contract" not in outputs:
        outputs["work_contract"] = build_work_contract(
            task_id=str(getattr(task, "task_id", "")),
            title=str(getattr(task, "title", "")),
            hypothesis=str(getattr(task, "hypothesis", "")),
            admission=outputs.get("admission"),
            purpose=scope["purpose"],
            delivery_required=scope["delivery_required"],
        )
    if "release_receipt" not in outputs:
        outputs["release_receipt"] = build_release_receipt(str(getattr(task, "task_id", "")))
    if refresh_evidence or "evidence_packet" not in outputs or outputs.get("evidence_packet", {}).get("origin") == "task_evidence_projection":
        outputs["evidence_packet"] = build_evidence_packet(task)
    # Responsibility completion is a projection of the same lifecycle, not a
    # second queue or approval path. Refresh derived fields while preserving
    # explicit learning/unknown/next-action annotations.
    existing_responsibility = outputs.get("responsibility_packet")
    responsibility = build_responsibility_packet(task, scope=scope)
    if isinstance(existing_responsibility, Mapping):
        for field in ("learning_return", "unknowns", "next_action"):
            if field in existing_responsibility:
                responsibility[field] = existing_responsibility[field]
        if "purpose" in existing_responsibility and str(existing_responsibility["purpose"]).strip():
            responsibility["purpose"] = existing_responsibility["purpose"]
    outputs["responsibility_packet"] = responsibility
    checks = {
        "work_contract": validate_work_contract(outputs.get("work_contract"), getattr(task, "task_id", None)),
        "evidence_packet": validate_evidence_packet(outputs.get("evidence_packet"), getattr(task, "task_id", None)),
        "release_receipt": validate_release_receipt(outputs.get("release_receipt"), getattr(task, "task_id", None)),
        "responsibility": validate_responsibility_packet(
            outputs.get("responsibility_packet"),
            task_id=getattr(task, "task_id", None),
            strict=False,
        ),
    }
    return {
        "active": True,
        "scope": scope,
        "work_contract": outputs["work_contract"],
        "evidence_packet": outputs["evidence_packet"],
        "release_receipt": outputs["release_receipt"],
        "responsibility_packet": outputs["responsibility_packet"],
        "checks": checks,
    }


def protocol_errors(
    protocols: Mapping[str, Any],
    *,
    require_evidence: bool = False,
    require_responsibility: bool = False,
) -> List[str]:
    errors: List[str] = []
    checks = protocols.get("checks", {}) if isinstance(protocols, Mapping) else {}
    for name, check in checks.items() if isinstance(checks, Mapping) else []:
        if isinstance(check, Mapping) and not check.get("valid"):
            errors.extend(f"{name}:{error}" for error in check.get("errors", []))
    if require_evidence and isinstance(protocols, Mapping) and protocols.get("active"):
        packet = protocols.get("evidence_packet", {})
        if not isinstance(packet, Mapping):
            errors.append("evidence_packet:not_ready")
        else:
            if packet.get("status") != "PASS":
                errors.append("evidence_packet:status_not_pass")
            if packet.get("completeness") == "INCOMPLETE_GAPS":
                errors.append("evidence_packet:incomplete_gaps")
            if not packet.get("independent_groups"):
                errors.append("evidence_packet:independent_groups_missing")
    if require_responsibility and isinstance(protocols, Mapping) and protocols.get("active"):
        packet = protocols.get("responsibility_packet")
        check = validate_responsibility_packet(packet, strict=True)
        if not check.get("valid"):
            errors.extend(f"responsibility:{error}" for error in check.get("errors", []))
    return errors
