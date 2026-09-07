"""ACE execution-discipline protocol.

This module turns the proven, narrow part of the OMX-inspired pilot into a
single deterministic task envelope.  It is deliberately a protocol helper,
not a scheduler, worker runtime, reviewer, or second source of truth.

The pilot did *not* prove mandatory planning, parallel execution, independent
review, or crash recovery.  Those mechanisms therefore remain explicit
constraints/unknowns in the envelope instead of becoming runtime behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


PROTOCOL_VERSION = "ACE-EXECUTION-DISCIPLINE-1.1"
START_PROTOCOL_VERSION = "ACE-START-PROTOCOL-2.0"
COMPLEXITIES = ("simple", "medium", "complex")

PIPELINE_STAGES = (
    "observe",
    "clarify",
    "plan",
    "route",
    "execute",
    "verify",
    "review",
    "stop",
)
STAGE_ORDER = {stage: index for index, stage in enumerate(PIPELINE_STAGES)}

_EVENT_STAGE = {
    "prepared": "observe",
    "clarified": "clarify",
    "planned": "plan",
    "routed": "route",
    "started": "execute",
    "researched": "execute",
    "verified": "verify",
    "validated": "verify",
    "reviewed": "review",
    "guardian_reviewed": "review",
    "approved": "review",
    "archived": "stop",
    "stop": "stop",
}

_COMPLEX_TAGS = {
    "complex",
    "complexity:complex",
    "architecture",
    "migration",
    "integration",
    "multi_step",
    "multi-step",
    "cross_system",
    "audit",
}
_MEDIUM_TAGS = {"medium", "complexity:medium", "research", "implementation", "review"}
_COMPLEX_WORDS = ("架构", "迁移", "集成", "跨系统", "全链路", "复杂", "重构", "migration", "architecture", "integrat")
_MEDIUM_WORDS = ("研究", "审计", "实现", "修复", "验证", "research", "audit", "implement", "repair", "review")


def _normalise_tags(tags: Optional[Iterable[str]]) -> set[str]:
    return {str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()}


def classify_complexity(
    title: str,
    hypothesis: str = "",
    priority: str = "medium",
    tags: Optional[Iterable[str]] = None,
    depends_on: Optional[Iterable[str]] = None,
    explicit: Optional[str] = None,
) -> tuple[str, str]:
    """Return a conservative complexity and the evidence used to classify it."""

    if explicit in COMPLEXITIES:
        return explicit, "explicit"
    lowered = f"{title} {hypothesis}".lower()
    tagset = _normalise_tags(tags)
    if tagset & _COMPLEX_TAGS:
        return "complex", "tag"
    if any(word in lowered for word in _COMPLEX_WORDS):
        return "complex", "title_or_hypothesis"

    score = 0
    if priority in {"critical", "high"}:
        score += 1
    if len(list(depends_on or [])) >= 1:
        score += 1
    if tagset & _MEDIUM_TAGS:
        score += 1
    if any(word in lowered for word in _MEDIUM_WORDS):
        score += 1
    if score >= 2:
        return "medium", "bounded_heuristic"
    return "simple", "default_light_branch"


def _unknowns(admission: Optional[Dict[str, Any]]) -> List[str]:
    unknowns = [
        "Outcome is not independently verified until the existing Validator/Guardian path completes.",
        "Provider/model/token cost is unknown unless an execution trace is recorded.",
    ]
    if not admission:
        unknowns.append("No structured admission record was supplied.")
    return unknowns


def build_execution_discipline(
    *,
    title: str,
    hypothesis: str = "",
    priority: str = "medium",
    tags: Optional[Iterable[str]] = None,
    depends_on: Optional[Iterable[str]] = None,
    admission: Optional[Dict[str, Any]] = None,
    explicit_complexity: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the persisted, auditable envelope for a newly admitted task."""

    complexity, basis = classify_complexity(
        title,
        hypothesis,
        priority,
        tags,
        depends_on,
        explicit_complexity,
    )
    structured = complexity in {"medium", "complex"}
    now = datetime.now().isoformat()
    admission = admission if isinstance(admission, dict) else {}
    goal = admission.get("expected_result") or hypothesis or title
    verification = admission.get("verification_method") or "Existing Validator/Guardian path and source recheck."
    boundary = admission.get("risk") or "No external send, deployment, provider action, or production authority is granted by this envelope."
    phases = ["clarify_optional", "execute", "verify", "stop"]
    if structured:
        phases = ["clarify", "minimal_plan", "execute", "verify", "stop"]
    pipeline = {
        stage: {
            "status": "pending",
            "required": stage in {"observe", "execute", "verify", "stop"}
            or (structured and stage in {"clarify", "plan", "route", "review"}),
            "evidence": [],
        }
        for stage in PIPELINE_STAGES
    }
    pipeline["observe"]["status"] = "ready"
    if structured:
        pipeline["clarify"]["status"] = "ready"
        pipeline["plan"]["status"] = "ready"
    else:
        pipeline["clarify"]["status"] = "skipped_light_branch"
        pipeline["plan"]["status"] = "skipped_light_branch"
    route = evaluate_route(
        complexity=complexity,
        depends_on=depends_on,
        shared_state=bool(admission.get("shared_state", False)),
        explicitly_independent=bool(admission.get("independent_lanes", False)),
    )

    return {
        "protocol": PROTOCOL_VERSION,
        "start_protocol": START_PROTOCOL_VERSION,
        "status": "prepared",
        "complexity": complexity,
        "classification_basis": basis,
        "mode": "structured" if structured else "light",
        "source": "ace_task_admission",
        "created_at": now,
        "last_event": "prepared",
        "clarification": {
            "status": "recorded_from_admission" if admission else "recorded_with_unknowns",
            "goal": goal,
            "non_goals": [
                "Do not infer production success from a proposal, report, or self-attestation.",
                "Do not create a second scheduler, router, queue, or runtime.",
            ],
            "known_facts": list(admission.get("evidence", [])) if isinstance(admission.get("evidence"), list) else [],
            "unknowns": _unknowns(admission),
            "boundary": boundary,
        },
        "minimal_plan": {
            "status": "required" if structured else "not_required",
            "steps": [
                "Re-read the source and current runtime/workspace state.",
                "Execute only the smallest task-scoped action.",
                "Run the existing verification path and preserve evidence gaps.",
            ] if structured else [],
        },
        "verification": {
            "method": verification,
            "required": structured,
            "reviewer": "existing_ace_validator_guardian",
            "independent_reviewer": "not_proven_by_pilot",
        },
        "constraints": {
            "parallelism": "refuse_by_default_for_shared_or_dependent_state",
            "parallelism_decision": route["decision"],
            "route": route,
            "independent_review": "deferred_until_separately_evidenced",
            "recovery": "use_existing_continue_gate_only",
            "external_side_effects": "not_authorized_by_protocol",
        },
        "stop": {
            "required": True,
            "conditions": [
                "Verification complete or an explicit evidence gap is recorded.",
                "Unknown/failed state is preserved instead of being retried blindly.",
                "No further in-scope action remains for this lifecycle pass.",
            ],
            "reason": "",
        },
        "phases": phases,
        "pipeline": pipeline,
        "checkpoints": [],
        "evidence_ledger": {
            "source": [],
            "runtime": [],
            "result": [],
            "review": [],
            "unknown": list(_unknowns(admission)),
        },
        "events": [{"event": "prepared", "at": now, "actor": "task_admission"}],
    }


def record_event(task: Any, event: str, actor: str = "ace", **details: Any) -> None:
    """Append a bounded protocol event to a Task-like object in place."""

    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        return
    envelope = outputs.get("execution_discipline")
    if not isinstance(envelope, dict):
        return
    events = envelope.setdefault("events", [])
    item = {"event": event, "actor": actor, "at": datetime.now().isoformat()}
    item.update({key: value for key, value in details.items() if value is not None})
    events.append(item)
    del events[:-50]
    envelope["last_event"] = event
    stage = _EVENT_STAGE.get(event)
    pipeline = envelope.setdefault("pipeline", {})
    if stage and isinstance(pipeline, dict):
        stage_record = pipeline.setdefault(stage, {"status": "pending", "required": True, "evidence": []})
        stage_record["status"] = "complete" if event not in {"started", "stop"} else (
            "in_progress" if event == "started" else "complete"
        )
        stage_record["last_event"] = event
        evidence = details.get("evidence")
        if evidence is not None:
            values = evidence if isinstance(evidence, list) else [evidence]
            for value in values:
                if value not in stage_record.setdefault("evidence", []):
                    stage_record["evidence"].append(value)
            del stage_record["evidence"][:-20]
    if event == "stop":
        envelope["status"] = "stopped"
        envelope.setdefault("stop", {})["reason"] = details.get("reason", "")
    elif event == "lifecycle_transition":
        target = details.get("to_status")
        if target == "active":
            envelope["status"] = "in_progress"
        elif target in {"blocked", "rejected", "archived", "graveyard"}:
            envelope["status"] = "stopped"
    elif event in {"verified", "approved", "archived"}:
        envelope["status"] = event
    elif event in {"started", "researched", "validated", "reviewed", "guardian_reviewed"}:
        envelope["status"] = "in_progress"


def record_checkpoint(
    task: Any,
    name: str,
    *,
    status: str = "recorded",
    evidence: Optional[Iterable[Any]] = None,
    actor: str = "ace",
    **details: Any,
) -> None:
    """Persist a bounded, replay-safe checkpoint without creating a new runtime."""

    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        return
    envelope = outputs.get("execution_discipline")
    if not isinstance(envelope, dict):
        return
    checkpoints = envelope.setdefault("checkpoints", [])
    item = {
        "name": str(name),
        "status": str(status),
        "actor": actor,
        "at": datetime.now().isoformat(),
        "evidence": list(evidence or [])[:20],
    }
    item.update({key: value for key, value in details.items() if value is not None})
    checkpoints.append(item)
    del checkpoints[:-20]


def add_evidence_ledger_entry(task: Any, kind: str, value: Any) -> None:
    """Add evidence to the protocol ledger while preserving unknowns."""

    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        return
    envelope = outputs.get("execution_discipline")
    if not isinstance(envelope, dict):
        return
    ledger = envelope.setdefault("evidence_ledger", {})
    bucket = ledger.setdefault(kind if kind in {"source", "runtime", "result", "review", "unknown"} else "unknown", [])
    if value not in bucket:
        bucket.append(value)
    del bucket[:-50]


def evaluate_route(
    *,
    complexity: str,
    depends_on: Optional[Iterable[str]] = None,
    shared_state: bool = False,
    explicitly_independent: bool = False,
) -> Dict[str, Any]:
    """Decide the route without starting workers or a second coordination plane."""

    dependencies = list(depends_on or [])
    if shared_state or dependencies or not explicitly_independent:
        decision = "serial_existing_lifecycle"
        reason = "shared_or_dependent_or_unproven_independence"
    elif complexity == "simple":
        decision = "direct_light_branch"
        reason = "simple_task"
    else:
        decision = "serial_existing_lifecycle"
        reason = "parallelism_not_proven_by_pilot"
    return {
        "decision": decision,
        "reason": reason,
        "parallelism": "refused" if decision != "parallel_candidate" else "candidate_only",
        "worker_runtime": "not_started",
    }


def ensure_execution_discipline(task: Any) -> Dict[str, Any]:
    """Backfill the envelope for legacy tasks without changing their semantics."""

    outputs = getattr(task, "outputs", None)
    if not isinstance(outputs, dict):
        outputs = {}
        task.outputs = outputs
    envelope = outputs.get("execution_discipline")
    if isinstance(envelope, dict) and envelope.get("protocol") == PROTOCOL_VERSION:
        return envelope
    envelope = build_execution_discipline(
        title=getattr(task, "title", ""),
        hypothesis=getattr(task, "hypothesis", ""),
        priority=getattr(task, "priority", "medium"),
        tags=getattr(task, "tags", []),
        depends_on=getattr(task, "depends_on", []),
        admission=outputs.get("admission") if isinstance(outputs.get("admission"), dict) else None,
    )
    envelope["source"] = "legacy_task_backfill"
    outputs["execution_discipline"] = envelope
    return envelope


def execution_gate(task: Any, *, allow_backfill: bool = True) -> tuple[bool, str]:
    """Check the minimum pre-execution envelope without invoking any model."""

    outputs = getattr(task, "outputs", None)
    existing = outputs.get("execution_discipline") if isinstance(outputs, dict) else None
    if not isinstance(existing, dict) and not allow_backfill:
        return False, "execution_discipline_missing_envelope"
    envelope = ensure_execution_discipline(task) if allow_backfill else existing
    if envelope.get("complexity") not in {"medium", "complex"}:
        return True, "light_branch"
    clarification = envelope.get("clarification")
    plan = envelope.get("minimal_plan")
    verification = envelope.get("verification")
    if not isinstance(clarification, dict) or not str(clarification.get("goal", "")).strip():
        return False, "execution_discipline_missing_goal"
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list) or not plan["steps"]:
        return False, "execution_discipline_missing_minimal_plan"
    if not isinstance(verification, dict) or not str(verification.get("method", "")).strip():
        return False, "execution_discipline_missing_verification"
    if not str(clarification.get("boundary", "")).strip():
        return False, "execution_discipline_missing_boundary"
    if envelope.get("protocol") != PROTOCOL_VERSION:
        return False, "execution_discipline_protocol_mismatch"
    if envelope.get("start_protocol") != START_PROTOCOL_VERSION:
        return False, "execution_discipline_start_protocol_mismatch"
    return True, "structured_envelope_ready"


def validate_execution_discipline(task: Any) -> Dict[str, Any]:
    """Validate the protocol envelope without invoking a worker or changing state.

    This is intentionally a pure audit helper.  It catches the class of drift
    that an OMX-style workflow can hide: fields exist, but the recorded events
    do not describe a legal progression or a stopped task has no reason.
    """

    errors: List[str] = []
    warnings: List[str] = []
    outputs = getattr(task, "outputs", None)
    envelope = outputs.get("execution_discipline") if isinstance(outputs, dict) else None
    # Validation is an observation path.  Do not backfill or repair a missing
    # envelope while claiming to audit it; doing so would turn a damaged record
    # into a green receipt and would make independent acceptance self-fulfilling.
    if not isinstance(envelope, dict):
        return {
            "valid": False,
            "protocol": None,
            "complexity": None,
            "status": None,
            "errors": ["missing_execution_discipline_envelope"],
            "warnings": [],
            "last_event": None,
            "required_stages": [],
            "event_count": 0,
        }
    complexity = envelope.get("complexity")
    if complexity not in COMPLEXITIES:
        errors.append("invalid_complexity")
    if envelope.get("protocol") != PROTOCOL_VERSION:
        errors.append("protocol_mismatch")
    if envelope.get("start_protocol") != START_PROTOCOL_VERSION:
        errors.append("start_protocol_mismatch")

    pipeline = envelope.get("pipeline")
    if not isinstance(pipeline, dict):
        errors.append("missing_pipeline")
        pipeline = {}
    required_stages = [
        stage for stage in PIPELINE_STAGES
        if isinstance(pipeline.get(stage), dict) and pipeline[stage].get("required")
    ]
    for stage in required_stages:
        if not isinstance(pipeline.get(stage, {}).get("evidence", []), list):
            errors.append(f"invalid_stage_evidence:{stage}")

    events = envelope.get("events", [])
    if not isinstance(events, list):
        errors.append("invalid_events")
        events = []
    last_stage = -1
    for item in events:
        if not isinstance(item, dict):
            errors.append("invalid_event_record")
            continue
        stage = _EVENT_STAGE.get(item.get("event"))
        if not stage:
            continue
        index = STAGE_ORDER[stage]
        if index < last_stage:
            errors.append(f"stage_regression:{stage}")
        last_stage = max(last_stage, index)

    status = envelope.get("status")
    stop = envelope.get("stop")
    if status == "stopped":
        if not isinstance(stop, dict) or not str(stop.get("reason", "")).strip():
            errors.append("stopped_without_reason")
    elif status in {"prepared", "in_progress", "verified", "reviewed", "approved"}:
        warnings.append("lifecycle_not_stopped")
    if complexity == "simple":
        warnings.append("light_branch_no_required_plan")

    return {
        "valid": not errors,
        "protocol": envelope.get("protocol"),
        "complexity": complexity,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "last_event": envelope.get("last_event"),
        "required_stages": required_stages,
        "event_count": len(events),
    }


def protocol_receipt(task: Any) -> Dict[str, Any]:
    """Return a compact, JSON-safe audit receipt for a task's protocol state."""

    audit = validate_execution_discipline(task)
    outputs = getattr(task, "outputs", None)
    envelope = outputs.get("execution_discipline") if isinstance(outputs, dict) else None
    envelope = envelope if isinstance(envelope, dict) else {}
    return {
        "receipt_version": "ACE-START-PROTOCOL-RECEIPT-1.0",
        "task_id": getattr(task, "task_id", ""),
        "protocol": audit["protocol"],
        "start_protocol": envelope.get("start_protocol"),
        "valid": audit["valid"],
        "complexity": audit["complexity"],
        "status": audit["status"],
        "last_event": audit["last_event"],
        "required_stages": audit["required_stages"],
        "event_count": audit["event_count"],
        "unknown_count": len(envelope.get("clarification", {}).get("unknowns", [])),
        "errors": audit["errors"],
        "warnings": audit["warnings"],
    }
