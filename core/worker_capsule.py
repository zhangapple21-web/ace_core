"""Bounded task capsules for stateless (weak-model) workers.

ACE-QWEN-FIELD-01.  The premise of this module is that a worker may be
interchangeable, forgetful, wrong, and may die mid-task.  Everything the
worker is allowed to know, and everything it must hand back, is therefore
rendered from and written through the *existing* single source of truth:
``core.task.TaskPool`` records plus the ``execution_discipline`` envelope
already stored in ``task.outputs``.

This module is deliberately NOT:

* a scheduler, queue, lease service, or second TaskPool;
* a worker runtime, reviewer, or validator;
* a place that stores state of its own.

It only adds two narrow ports:

* :func:`render_task_capsule` — hand one leased worker a bounded brief whose
  content is a projection of already-persisted fields (fail-closed on any
  credential or envelope problem, and it never backfills what it renders).
* :func:`submit_task_capsule_result` — take a bounded result payload back
  through the existing ``TaskPool`` update/move path, so the worker's
  evidence lands on the task record instead of in a side document.

The capsule text contains no wall-clock reads, so the same stored task state
always renders to the same ``capsule_hash``; time-relative values are
returned outside the hashed body as metadata for the caller.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .execution_discipline import (
    PIPELINE_STAGES,
    add_evidence_ledger_entry,
    record_checkpoint,
    record_event,
    validate_execution_discipline,
)

CAPSULE_VERSION = "ace.worker_capsule.v1"
SUBMIT_RECEIPT_VERSION = "ace.worker_capsule.submit-receipt.v1"

# A weak worker must be able to hold the whole brief in its head at once.
CAPSULE_CHAR_BUDGET = 6000
_MAX_LINES_PER_SECTION = 8
_MAX_LINE_CHARS = 220
_MAX_CHECKPOINTS_SHOWN = 5

_TRANSITION_TARGETS = ("", "review", "blocked", "pending")

ALLOWED_SUBMIT_KEYS = frozenset(
    {
        "summary",
        "facts",
        "evidence",
        "unknowns",
        "objections",
        "next_verification",
        "stop_condition",
        "checkpoint_name",
        "transition",
        "reason",
    }
)

# Rendered verbatim from the envelope's own stage names; these are pointers at
# fields the worker can re-read, not new rules.  Keep them declarative: the
# normative source stays ``execution_discipline`` + ``execution_contract``.
_STAGE_HINTS: Dict[str, str] = {
    "observe": "只依据本胶囊与 task 记录已有字段工作，胶囊之外的都不要假设。",
    "clarify": "把不清楚的部分写进 unknowns 交回，不要自己补事实。",
    "plan": "只做 minimal_plan.steps 里最小的那一步，不扩范围。",
    "route": "constraints.route 已决定串行/并行，不得自行改路由。",
    "execute": "执行局部动作，并为每个结论留下可复核的 evidence source。",
    "verify": "自检 evidence 是否可复算；不能复算的写进 unknowns。",
    "review": "等既有 Validator/Guardian 判定，不要自行宣布 VERIFIED。",
    "stop": "留下停止原因并交回，不要重试式空转。",
}

_PORT_FORBIDDEN = [
    "不要直接编辑 task_pool 下的 JSON 文件，也不要新建第二套任务池/队列/调度器。",
    "不要用 move_task 绕过 submit 端口把任务推到 approved/archived。",
    "不要把模型输出、报告或本胶囊自身当成已验证事实。",
    "不要执行胶囊 boundary 之外或 external_side_effects 未授权的动作。",
]


def _now() -> datetime:
    return datetime.now()


def _one_line(value: Any, limit: int = _MAX_LINE_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    for noise in ("\r\n", "\r", "\n", "\t"):
        text = text.replace(noise, " ")
    text = " ".join(text.split()).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def _section_lines(items: List[Any]) -> Tuple[List[str], int]:
    lines: List[str] = []
    for item in items:
        rendered = _one_line(item)
        if rendered:
            lines.append(f"- {rendered}")
    omitted = max(0, len(lines) - _MAX_LINES_PER_SECTION)
    return lines[:_MAX_LINES_PER_SECTION], omitted


def _digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _lease_state(task: Any, reference: Optional[datetime] = None) -> Tuple[str, Optional[float]]:
    """Classify the stored lease as ``leased`` / ``expired`` / ``absent``."""

    raw = str(getattr(task, "lease_expires_at", "") or "")
    if not raw:
        return "absent", None
    moment = reference or _now()
    try:
        expires = datetime.fromisoformat(raw)
    except ValueError:
        return "expired", None
    return ("expired" if expires <= moment else "leased"), (expires - moment).total_seconds()


def _refusal(reason: str, task_id: str, hint: str, **extra: Any) -> Dict[str, Any]:
    result = {
        "status": "REFUSED",
        "reason": reason,
        "task_id": task_id,
        "capsule_version": CAPSULE_VERSION,
        "recovery_hint": hint,
        "capsule_text": None,
        "runtime_mutation": False,
    }
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def _envelope_of(task: Any) -> Dict[str, Any]:
    outputs = getattr(task, "outputs", None)
    envelope = outputs.get("execution_discipline") if isinstance(outputs, dict) else None
    return envelope if isinstance(envelope, dict) else {}


def _next_stage(envelope: Dict[str, Any]) -> Tuple[str, str]:
    pipeline = envelope.get("pipeline")
    if not isinstance(pipeline, dict) or not pipeline:
        return "observe", _STAGE_HINTS["observe"]
    for stage in PIPELINE_STAGES:
        record = pipeline.get(stage)
        if not isinstance(record, dict):
            continue
        if not record.get("required"):
            continue
        if str(record.get("status")) not in {"complete", "skipped_light_branch"}:
            return stage, _STAGE_HINTS.get(stage, "")
    return "stop", _STAGE_HINTS["stop"]


def check_capsule_authority(
    task_pool: Any,
    task_id: str,
    *,
    claim_id: str,
    fencing_token: int,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """The one ruler that answers "may this caller touch this task right now".

    Returns ``{"status": "AUTHORIZED", "task": task, "lease_seconds_remaining": n}``
    or a refusal.  Render uses it, and so must every *write* port that the pool
    itself does not fence (e.g. ``TaskPool.fail_task``: it takes a task id and
    moves it regardless of who holds the lease).  Keeping the rule here means one
    rule has one enforcement point instead of a read gate and an ad-hoc write
    check that drift apart.

    It deliberately stops short of the envelope check: a task with a damaged
    envelope must not be rendered as a healthy brief, but its holder must still
    be able to record an honest failure against it.
    """

    if not isinstance(task_id, str) or not task_id.strip():
        return _refusal("capsule_task_id_missing", task_id or "", "call render_task_capsule with a real task_id")
    task_id = task_id.strip()
    if not isinstance(claim_id, str) or not claim_id.strip():
        return _refusal("capsule_claim_id_missing", task_id, "claim the task first via core.ace_start.ace_start")
    if not isinstance(fencing_token, int) or isinstance(fencing_token, bool) or fencing_token <= 0:
        return _refusal("capsule_fencing_token_invalid", task_id, "fencing_token must be a positive int from ace_start")

    task = task_pool.load_task(task_id)
    if task is None:
        return _refusal("task_not_found", task_id, "the task record is not in any pool bucket")

    status = str(getattr(task, "status", ""))
    if status != "active":
        return _refusal(
            f"capsule_task_not_active:{status}",
            task_id,
            "start the task with ace_start (pending -> active) before rendering",
        )

    stored_claim = str(getattr(task, "claim_id", "") or "")
    if not stored_claim:
        return _refusal("capsule_unleased_active_record", task_id, "run TaskPool.reclaim_stale_leases then ace_start again")
    if stored_claim != claim_id.strip():
        # Never echo the real claim id: a wrong worker must not be able to read it.
        return _refusal("capsule_claim_mismatch", task_id, "your claim_id is not the current lease owner; re-start the task")
    if int(getattr(task, "fencing_token", 0) or 0) != fencing_token:
        return _refusal(
            "capsule_fencing_token_stale",
            task_id,
            "another claim superseded this one; stop writing and re-render after a fresh ace_start",
        )

    lease, seconds_remaining = _lease_state(task, now)
    if lease == "expired":
        return _refusal(
            "capsule_lease_expired",
            task_id,
            "renew_lease before continuing, or let reclaim_stale_leases return the task to pending",
            lease_expires_at=getattr(task, "lease_expires_at", ""),
        )
    if lease == "absent":
        return _refusal("capsule_lease_absent", task_id, "TaskPool.recover_incomplete_transitions then ace_start again")

    return {
        "status": "AUTHORIZED",
        "task_id": task_id,
        # ``task`` is the live record, not wire data: an AUTHORIZED dict must never
        # be serialised as-is.  Only the refusal shape is emitted by callers.
        "task": task,
        "capsule_version": CAPSULE_VERSION,
        "runtime_mutation": False,
        "lease_seconds_remaining": seconds_remaining,
        "claim_id": stored_claim,
        "fencing_token": int(getattr(task, "fencing_token", 0) or 0),
    }


def recover_worker_leases(
    task_pool: Any,
    *,
    owner: str,
    task_id: Optional[str] = None,
    now: Optional[datetime] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Answer the one question a stateless worker cannot answer after a cold restart.

    A weak worker's whole context can vanish mid-lease: its shell history, the
    ``claim_id`` and the ``fencing_token`` go with it.  Every other port needs
    those credentials, so ``start`` refuses (``taskpool_claim_rejected``) and the
    worker is locked out of a task it still owns until the lease expires and a
    scheduler pass reclaims it.  This is the read-only door back in.

    Trust model, stated plainly: ``TaskPool.claim_task`` identifies a worker by a
    self-declared ``owner`` name, so re-attestation by the same name is no weaker
    than the original claim.  It is also no *stronger* -- anything that can name
    itself ``owner`` can read that owner's live claim.  Callers that need real
    isolation must pass an owner name that is not guessable.

    Live leases for ``owner`` are returned with their credentials; expired ones
    are listed **without** credentials, because handing a dead lease to whoever
    asks would turn this door into the zombie write the drill already proves is
    blocked.  No pool write happens on any path (``runtime_mutation`` is False).
    """

    if not isinstance(owner, str) or not owner.strip():
        return _refusal("capsule_owner_missing", task_id or "", "pass the same --owner string you used with start")
    owner = owner.strip()

    candidates = [t for t in task_pool.list_tasks(status="active", limit=limit) if str(getattr(t, "lease_owner", "") or "") == owner]
    if task_id is not None and str(task_id).strip():
        candidates = [t for t in candidates if str(getattr(t, "task_id", "")) == str(task_id).strip()]

    rows, expired, unleased = [], [], []
    for task in candidates:
        stored_claim = str(getattr(task, "claim_id", "") or "")
        lease, seconds_remaining = _lease_state(task, now)
        if not stored_claim:
            unleased.append(str(getattr(task, "task_id", "")))
            continue
        if lease != "leased":
            expired.append(
                {
                    "task_id": str(getattr(task, "task_id", "")),
                    "lease_state": lease,
                    "lease_expires_at": _one_line(getattr(task, "lease_expires_at", ""), 40),
                    "fencing_token": int(getattr(task, "fencing_token", 0) or 0),
                }
            )
            continue
        rows.append(
            {
                "task_id": str(getattr(task, "task_id", "")),
                "title": _one_line(getattr(task, "title", ""), 120),
                "claim_id": stored_claim,
                "fencing_token": int(getattr(task, "fencing_token", 0) or 0),
                "lease_seconds_remaining": round(seconds_remaining, 3) if seconds_remaining is not None else None,
                "next_command": (
                    f"python -m ops.worker_capsule_cli render --task-id {getattr(task, 'task_id', '')} "
                    f"--claim {stored_claim} --token {int(getattr(task, 'fencing_token', 0) or 0)}"
                ),
            }
        )

    if rows:
        hint = "re-render with the next_command above -- do NOT call start again, it will refuse a live lease"
    else:
        hint = "no live lease held by this owner; run list-pending and start a task"
        if expired:
            hint = "the lease is expired, not lost: run TaskPool.reclaim_stale_leases, then start again"
        elif unleased:
            hint = "active records held by this owner carry no claim_id; run recover_incomplete_transitions then start again"
        elif candidates:
            hint = "this owner holds matching records only outside the active bucket"

    return {
        "status": "LEASES_FOUND" if rows else "NO_LIVE_LEASE",
        "owner": owner,
        "count": len(rows),
        "leases": rows,
        "expired_claims": expired,
        "unleased_active_records": unleased,
        "hint": hint,
        "runtime_mutation": False,
    }


def render_task_capsule(
    task_pool: Any,
    task_id: str,
    *,
    claim_id: str,
    fencing_token: int,
    char_budget: int = CAPSULE_CHAR_BUDGET,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Render the bounded brief for the worker currently holding ``task_id``.

    Read-only against the TaskPool.  Refuses (without mutating anything) when
    the task is missing, not actively leased, when the supplied claim
    credentials do not match the stored record, when the lease has expired, or
    when the persisted envelope is absent/damaged — a missing envelope is
    reported, never silently rebuilt, so a broken record cannot masquerade as
    a healthy assignment.
    """

    authority = check_capsule_authority(
        task_pool,
        task_id,
        claim_id=claim_id,
        fencing_token=fencing_token,
        now=now,
    )
    if authority.get("status") != "AUTHORIZED":
        return authority
    task = authority["task"]
    seconds_remaining = authority.get("lease_seconds_remaining")

    envelope = _envelope_of(task)
    if not envelope:
        return _refusal(
            "capsule_envelope_missing",
            task_id,
            "outputs.execution_discipline is absent; this record must be repaired by the pool owner, not by a worker",
        )
    audit = validate_execution_discipline(task)
    if not audit.get("valid"):
        return _refusal(
            "capsule_envelope_invalid",
            task_id,
            "persisted envelope failed validation; preserve it as-is and escalate instead of executing",
            envelope_errors=list(audit.get("errors", [])),
        )

    clarification = envelope.get("clarification") or {}
    plan = envelope.get("minimal_plan") or {}
    verification = envelope.get("verification") or {}
    constraints = envelope.get("constraints") or {}
    stop = envelope.get("stop") or {}
    ledger = envelope.get("evidence_ledger") or {}
    admission = (getattr(task, "outputs", {}) or {}).get("admission") or {}

    omitted: Dict[str, int] = {}
    lines: List[str] = []
    lines.append(f"[ACE_TASK_CAPSULE version={CAPSULE_VERSION}]")
    lines.append(
        "你是被 ACE 外部结构托住的一次性执行节点：可以死，任务不能死；"
        "只依据本胶囊内已持久化的字段工作。"
    )

    lines.append("== IDENTITY ==")
    lines.append(f"- task_id: {task_id}")
    lines.append(f"- title: {_one_line(getattr(task, 'title', ''))}")
    lines.append(f"- hypothesis: {_one_line(getattr(task, 'hypothesis', '')) or '(none)'}")
    lines.append(
        "- claim: "
        f"owner={_one_line(getattr(task, 'lease_owner', '')) or '(unnamed)'} "
        f"fencing_token={int(getattr(task, 'fencing_token', 0) or 0)} "
        f"lease_expires_at={_one_line(getattr(task, 'lease_expires_at', ''))}"
    )
    lines.append(
        f"- attempt: retry_count={int(getattr(task, 'retry_count', 0) or 0)} "
        f"last_claimed_at={_one_line(getattr(task, 'last_claimed_at', '')) or '(never)'}"
    )
    lines.append(
        f"- envelope: complexity={envelope.get('complexity')} mode={envelope.get('mode')} "
        f"status={envelope.get('status')} protocol={envelope.get('protocol')}"
    )

    goal_lines, goal_omitted = _section_lines([clarification.get("goal", "") or "(no goal recorded)"])
    omitted["goal"] = goal_omitted
    lines.append("== GOAL ==")
    lines.extend(goal_lines)

    ng_lines, ng_omitted = _section_lines(list(clarification.get("non_goals") or []))
    omitted["non_goals"] = ng_omitted
    lines.append("== NON-GOALS ==")
    lines.extend(ng_lines or ["- (none recorded)"])

    lines.append("== BOUNDARY (allowed scope) ==")
    lines.append(f"- {_one_line(clarification.get('boundary') or '(no boundary recorded)')}")
    lines.append(f"- external_side_effects: {_one_line(constraints.get('external_side_effects'))}")
    lines.append(f"- parallelism: {_one_line(constraints.get('parallelism'))}")
    lines.append(f"- recovery: {_one_line(constraints.get('recovery'))}")

    known = list(clarification.get("known_facts") or []) + list(admission.get("evidence") or [])
    # ``clarification.known_facts`` is copied from ``admission.evidence`` at
    # admission time; rendering both made one piece of evidence look like two,
    # which is exactly the miscount a weak worker cannot self-check.
    deduped_known: List[Any] = []
    seen_known: set[str] = set()
    for item in known:
        key = _one_line(item)
        if key and key not in seen_known:
            seen_known.add(key)
            deduped_known.append(item)
    kf_lines, kf_omitted = _section_lines(deduped_known)
    omitted["known_facts"] = kf_omitted
    lines.append("== KNOWN FACTS (already admitted) ==")
    lines.extend(kf_lines or ["- (none admitted; treat the task as un-evidenced)"])

    un_lines, un_omitted = _section_lines(list(clarification.get("unknowns") or []))
    omitted["unknowns"] = un_omitted
    lines.append("== UNKNOWNS (keep them unknown) ==")
    lines.extend(un_lines or ["- (none recorded)"])

    plan_lines, plan_omitted = _section_lines(list(plan.get("steps") or []))
    omitted["minimal_plan"] = plan_omitted
    lines.append(f"== MINIMAL PLAN ({plan.get('status', 'unknown')}) ==")
    lines.extend(plan_lines or ["- (light branch: no plan required)"])

    lines.append("== VERIFICATION ==")
    lines.append(f"- method: {_one_line(verification.get('method'))}")
    lines.append(f"- reviewer: {_one_line(verification.get('reviewer'))}")
    lines.append(f"- independent_reviewer: {_one_line(verification.get('independent_reviewer'))}")
    lines.append(f"- required: {bool(verification.get('required'))}")

    stage, hint = _next_stage(envelope)
    lines.append("== NEXT ACTION ==")
    lines.append(f"- stage: {stage}")
    if hint:
        lines.append(f"- hint: {hint}")

    checkpoints = envelope.get("checkpoints") or []
    tail = checkpoints[-_MAX_CHECKPOINTS_SHOWN:] if isinstance(checkpoints, list) else []
    omitted["checkpoints"] = max(0, (len(checkpoints) if isinstance(checkpoints, list) else 0) - len(tail))
    lines.append("== CHECKPOINTS ALREADY ON THIS TASK ==")
    if tail:
        for item in tail:
            if isinstance(item, dict):
                lines.append(
                    f"- {_one_line(item.get('name'))} status={_one_line(item.get('status'))} "
                    f"actor={_one_line(item.get('actor'))} at={_one_line(item.get('at'))}"
                )
            else:
                lines.append(f"- {_one_line(item)}")
    else:
        lines.append("- (none yet)")

    ledger_view = {key: list(values or []) for key, values in ledger.items() if isinstance(ledger, dict)}
    counts = {key: len(values) for key, values in ledger_view.items()}
    pointers = {
        key: [f"{_one_line(entry, 120)}" for entry in values[-3:]]
        for key, values in ledger_view.items()
        if values
    }
    lines.append("== EVIDENCE LEDGER (counts) ==")
    lines.append(f"- {json.dumps(counts, ensure_ascii=False, sort_keys=True)}")
    if pointers:
        lines.append("- tail: " + _one_line(json.dumps(pointers, ensure_ascii=False, sort_keys=True), 400))

    lines.append("== FORBIDDEN ==")
    forbidden = list(ng_lines) + [f"- {row}" for row in _PORT_FORBIDDEN]
    lines.extend(forbidden)

    lines.append("== RETURN PROTOCOL ==")
    lines.append("- keep working: TaskPool.renew_lease(task_id, owner, claim_id, lease_seconds)")
    lines.append("- hand back: core.worker_capsule.submit_task_capsule_result(...)")
    lines.append("- cannot finish: TaskPool.fail_task(task_id, reason, actor, failure_type) with one of "
                 "retryable/permanent/manual_gate/external_condition")
    lines.append("- died mid-task: do nothing; reclaim_stale_leases returns the task to pending for the next worker")
    lines.append("== STOP ==")
    for condition in list(stop.get("conditions") or []):
        lines.append(f"- {_one_line(condition)}")

    body = "\n".join(lines)
    total_lines = len(lines)
    if len(body) > char_budget:
        suffix = "\n[TRUNCATED_BY_BUDGET — 原文超出胶囊预算，未截断的信息仍完整保存在 task 记录里]"
        keep = max(0, char_budget - len(suffix))
        body = body[:keep] + suffix
        omitted["body"] = omitted.get("body", 0) + 1

    capsule_hash = _digest({"capsule_version": CAPSULE_VERSION, "task_id": task_id, "text": body})
    return {
        "status": "CAPSULE_READY",
        "task_id": task_id,
        "capsule_version": CAPSULE_VERSION,
        "capsule_text": body,
        "capsule_hash": capsule_hash,
        "char_count": len(body),
        "char_budget": char_budget,
        "line_count": total_lines,
        "omitted": omitted,
        "next_stage": stage,
        "lease_seconds_remaining": round(seconds_remaining, 3) if seconds_remaining is not None else None,
        "lease_expires_at": _one_line(getattr(task, "lease_expires_at", ""), 40),
        "claim_id": authority["claim_id"],
        "fencing_token": authority["fencing_token"],
        "runtime_mutation": False,
    }


def _normalise_evidence(value: Any) -> Tuple[Optional[List[Dict[str, str]]], Optional[str]]:
    if not isinstance(value, list):
        return None, "capsule_evidence_not_a_list"
    rows: List[Dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            text = _one_line(item)
            if not text:
                return None, f"capsule_evidence_empty:{index}"
            rows.append({"content": text, "source": "worker-stated"})
            continue
        if not isinstance(item, dict):
            return None, f"capsule_evidence_not_a_string_or_object:{index}"
        content = _one_line(item.get("content", ""))
        source = _one_line(item.get("source", ""))
        if not content or not source:
            return None, f"capsule_evidence_needs_content_and_source:{index}"
        rows.append({"content": content, "source": source[:_MAX_LINE_CHARS]})
    return rows, None


def submit_task_capsule_result(
    task_pool: Any,
    task_id: str,
    *,
    claim_id: str,
    fencing_token: int,
    actor: str,
    payload: Any,
    seen_capsule_hash: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Write one worker's bounded result back through the existing pool path.

    Strict by design: unknown keys, unsourced evidence, or a stale claim are
    refused *before* anything is written, so a confused worker cannot create a
    second truth or land un-verifiable text on a task record.
    """

    if not isinstance(task_id, str) or not task_id.strip():
        return _refusal("capsule_task_id_missing", task_id or "", "supply a real task_id")
    task_id = task_id.strip()
    if not isinstance(actor, str) or not actor.strip():
        return _refusal("capsule_actor_missing", task_id, "actor must name the worker submitting")
    actor = actor.strip()
    if not isinstance(payload, dict):
        return _refusal("capsule_payload_not_a_mapping", task_id, "payload must be a JSON object")

    unknown_keys = sorted(str(key) for key in payload if str(key) not in ALLOWED_SUBMIT_KEYS)
    if unknown_keys:
        return _refusal(
            "capsule_payload_unknown_keys:" + ",".join(unknown_keys),
            task_id,
            "allowed keys are " + ",".join(sorted(ALLOWED_SUBMIT_KEYS)),
        )

    transition = payload.get("transition", "review")
    if transition is None:
        transition = ""
    if not isinstance(transition, str) or transition not in _TRANSITION_TARGETS:
        return _refusal(
            f"capsule_transition_not_allowed:{_one_line(transition, 60)}",
            task_id,
            "transition must be one of review/blocked/pending or an empty string",
        )

    for key in ("facts", "unknowns", "objections"):
        value = payload.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            return _refusal(f"capsule_{key}_must_be_a_list", task_id, f"{key} must be a list of strings")
        if any(not isinstance(entry, str) for entry in value):
            return _refusal(f"capsule_{key}_must_be_strings", task_id, f"{key} must be a list of strings")
    for key in ("summary", "next_verification", "stop_condition", "checkpoint_name", "reason"):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            return _refusal(f"capsule_{key}_must_be_a_string", task_id, f"{key} must be a single string")

    facts = list(payload.get("facts") or [])
    unknowns = list(payload.get("unknowns") or [])
    objections = list(payload.get("objections") or [])
    evidence_rows, evidence_error = _normalise_evidence(payload.get("evidence") or [])
    if evidence_error:
        return _refusal(evidence_error, task_id, "each evidence item must be a string or {content, source}")

    if not (facts or unknowns or objections or evidence_rows) and not str(payload.get("summary") or "").strip():
        return _refusal(
            "capsule_submit_without_content",
            task_id,
            "submit at least one of facts/evidence/unknowns/objections, or a summary; an empty hand-back is not progress",
        )

    gate = render_task_capsule(task_pool, task_id, claim_id=claim_id, fencing_token=fencing_token, now=now)
    if gate.get("status") != "CAPSULE_READY":
        return dict(gate, recovery_hint=str(gate.get("recovery_hint", "")) + " | nothing was written")

    task = task_pool.load_task(task_id)
    if task is None:
        return _refusal("task_not_found", task_id, "record vanished between gate and write; nothing was written")
    envelope = _envelope_of(task)

    for row in evidence_rows:
        task.add_evidence(row["content"], row["source"])
        add_evidence_ledger_entry(task, "result", f"{row['source']}::{row['content'][:80]}")
    for entry in facts:
        add_evidence_ledger_entry(task, "result", f"worker-fact::{_one_line(entry)}")
    for entry in unknowns:
        add_evidence_ledger_entry(task, "unknown", f"worker-unknown::{_one_line(entry)}")
    for entry in objections:
        add_evidence_ledger_entry(task, "review", f"worker-objection::{_one_line(entry)}")
    record_event(
        task,
        "researched",
        actor=actor,
        evidence=[f"{row['source']}" for row in evidence_rows] or [f"{actor}:{len(facts)} facts"],
    )
    summary = _one_line(payload.get("summary") or "", 1000)
    if summary:
        task.result = summary
    checkpoint_name = _one_line(payload.get("checkpoint_name") or "worker_submission", 60)
    record_checkpoint(
        task,
        checkpoint_name,
        actor=actor,
        evidence=[f"{row['source']}" for row in evidence_rows][:20],
        capsule_version=CAPSULE_VERSION,
        capsule_hash=str(seen_capsule_hash) if isinstance(seen_capsule_hash, str) and seen_capsule_hash else None,
        evidence_count=len(evidence_rows),
        facts_count=len(facts),
        unknowns_count=len(unknowns),
        objections_count=len(objections),
        reason=_one_line(payload.get("reason") or "", 200) or None,
    )

    if not task_pool.update_task(task):
        return _refusal(
            "capsule_write_rejected",
            task_id,
            "TaskPool.update_task refused the fenced write (stale claim or damaged record); nothing was committed",
        )

    moved = None
    if transition:
        moved = task_pool.move_task(task_id, transition, actor=actor, reason=f"capsule_submit:{checkpoint_name}", claim_id=claim_id)
        if moved is None:
            stored = task_pool.load_task(task_id)
            return _refusal(
                f"capsule_transition_rejected:{transition}",
                task_id,
                "evidence was recorded but the lifecycle move was refused by the existing gates",
                evidence_persisted=True,
                stored_status=getattr(stored, "status", "") if stored else None,
            )

    return {
        "status": "SUBMITTED",
        "receipt_version": SUBMIT_RECEIPT_VERSION,
        "task_id": task_id,
        "actor": actor,
        "claim_id": claim_id,
        "fencing_token": fencing_token,
        "evidence_count": len(evidence_rows),
        "facts_count": len(facts),
        "unknowns_count": len(unknowns),
        "objections_count": len(objections),
        "checkpoint_name": checkpoint_name,
        "capsule_hash": str(seen_capsule_hash) if isinstance(seen_capsule_hash, str) and seen_capsule_hash else None,
        "transition": transition or None,
        "stored_status": getattr(moved, "status", None) if moved is not None else "active",
        "runtime_mutation": True,
    }
