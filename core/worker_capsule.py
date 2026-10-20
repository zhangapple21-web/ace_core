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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .execution_discipline import (
    PIPELINE_STAGES,
    ExecutionDiscipline,
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

# The capsule is written for a worker that has a shell and nothing else, so its
# return protocol must name the port that worker can actually run.  This window
# built ``ops/worker_capsule_cli.py`` for exactly that reason; a capsule that
# only says ``TaskPool.renew_lease(...)`` hands the worker a brief it cannot
# execute and pushes it back into writing Python (capability 3/4/11 of
# ACE-QWEN-FIELD-01).  Repo root is static, so filling it in keeps the capsule
# hash clock-free and therefore reproducible.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PORT_MODULE = "ops.worker_capsule_cli"
_PORT_PY = "py -3.11"

# One-line meaning per submit key.  The *list* of keys stays
# ``ALLOWED_SUBMIT_KEYS`` (the ruler ``submit_task_capsule_result`` actually
# checks against); these entries only describe it, and a key that gains no
# description is caught by a fixture rather than silently going undocumented.
_SUBMIT_KEY_HINTS: Dict[str, str] = {
    "summary": "一句话结论；只交 summary 也算交回（全空会被拒）",
    "facts": "字符串列表：本次得到的事实，落进 evidence_ledger 的 result 桶",
    "evidence": "列表，每项 {content, source}（缺 source 的物件会被拒）；写成裸字符串也收，但 source 会被记成 worker-stated = 自评，不是可复算的指针",
    "unknowns": "字符串列表：不清楚的就原样交回，不要自己补事实",
    "objections": "字符串列表：对本次假设/做法的反对意见",
    "next_verification": "字符串：下一步该怎么复算这件事",
    "stop_condition": "字符串：什么条件下这条任务该停",
    "checkpoint_name": "字符串：本次交回的检查点名（省略则 worker_submission）",
    "transition": "review / blocked / pending / 空串（默认 review），其余值拒",
    "reason": "字符串：本次交回或转换的一句话理由",
}
_NO_DESCRIPTION = "(no description recorded)"


def pool_face(task_pool: Any) -> str:
    """The directory this render is reading, for copy-paste-ready port commands."""

    return str(getattr(task_pool, "pool_dir", "") or "<pool目录>")


def port_prefix(task_pool: Any) -> str:
    return f'cd "{_REPO_ROOT}" && {_PORT_PY} -m {_PORT_MODULE} --pool "{pool_face(task_pool)}"'


def _return_protocol_lines(task_pool: Any, task_id: str, claim_id: str, fencing_token: int, owner: str) -> List[str]:
    """The shell-shaped way back, one self-contained pasteable command per action.

    Two hard-won shapes, both measured rather than designed:

    * ``<占位>`` is input redirection in Windows cmd and ``a|b`` is a pipe, so a
      line carrying either exits 1 with no JSON at all -- which is worse than
      silent because the worker cannot tell a broken instruction from a refused
      one.  Holes are 【...】, enumerations use ``/``.
    * Prose on the same line as a command is part of the paste.  The first
      version of this face appended「（只读，……）」to the ``recover`` line and the
      literal-paste fixture fed argparse ``claim/token 一起还给你）`` as arguments.
      So each command sits alone on its own indented line, and each carries the
      whole prefix: a worker never has to assemble two lines into one command.

    Credentials come from the stored record, so the only things left to fill in
    are the file the worker wrote and the hash on its own render receipt.
    """

    actor = owner or "【你的worker名】"
    prefix = port_prefix(task_pool)
    creds = f"--task-id {task_id} --claim {claim_id} --token {int(fencing_token)}"

    def command(label: str, tail: str) -> List[str]:
        return [f"- {label}:", f"    {prefix} {tail}"]

    return [
        *command("找下一件活", "list-pending"),
        *command("还没做完，续租", f"renew {creds} --owner {actor} --lease 300"),
        *command(
            "要 capsule_hash（交回时填这个；本胶囊正文里没有它，因为它是对正文算出来的，重跑一次得到同一个值）",
            f"render {creds}",
        ),
        *command(
            "做完了，交回（把两个【】换成你写的文件路径和上一条回执里的 capsule_hash）",
            f"submit {creds} --actor {actor} --payload-file 【结果.json 的路径】 --capsule-hash 【capsule_hash】",
        ),
        *command(
            "做不动，别硬撑（--type 只能四选一，写错会被端口拒）",
            f"fail {creds} --actor {actor} --reason 【一句话原因】 --type 【retryable/permanent/manual_gate/external_condition】",
        ),
        *command(
            "交回后自检（只读，看这条任务现在真的落在哪个状态；转 review 后 list-pending 就看不见它了）",
            f"show --task-id {task_id}",
        ),
        *command("忘了凭证（只读，把你仍持有的任务连 claim/token 一起还给你）", f"recover --owner {actor}"),
        *command("租约过期（只重开自己这一件，不扫全池）", f"reclaim --task-id {task_id} --actor {actor}"),
        "- 注意: claim/token 只随 start 与 renew 的回执更新，换了凭证本胶囊即作废；交回后用「找下一件活」那条接着跑。",
    ]


def _submit_payload_lines() -> List[str]:
    """The accepted result shape, rendered from the key list the port enforces."""

    return [f"- {key}: {_SUBMIT_KEY_HINTS.get(key, _NO_DESCRIPTION)}" for key in sorted(ALLOWED_SUBMIT_KEYS)]


def _continuation(task_pool: Any, actor: str) -> Dict[str, Any]:
    """Capability 11: tell a stateless worker what to do *after* it handed back.

    A worker that finishes and then waits has, from ACE's point of view, died --
    the loop only continues if the hand-back receipt itself points at the next
    claimable work.  This is a read-only look at the same TaskPool; it ranks
    nothing and claims nothing, because priority stays the pool's job.  A failed
    read is reported as ``None`` rather than raised: the worker's write already
    landed and must not be made to look undone by the courtesy of a hint.
    """

    prefix = port_prefix(task_pool)
    listing: Dict[str, Any] = {"pending_now": None, "next_ids": [], "read_error": None}
    try:
        rows = list(task_pool.list_tasks(status="pending", limit=20) or [])
        listing["pending_now"] = len(rows)
        listing["next_ids"] = [str(getattr(row, "task_id", "")) for row in rows[:3] if getattr(row, "task_id", "")]
    except Exception as error:  # pragma: no cover - defensive, the pool owns this read
        listing["read_error"] = f"{type(error).__name__}: {_one_line(error)}"

    listing["next_commands"] = [
        f"{prefix} list-pending",
        f"{prefix} start --task-id 【从 list-pending 里挑的 id】 --owner {actor}",
        f"{prefix} render --task-id 【同一个 id】 --claim 【那次 start 的 claim_id】 --token 【它的 fencing_token】",
    ]
    listing["hint"] = (
        "凭证只随 start 的回执来：上一件任务的 claim/token 在新任务上无效。"
        "pending_now=0 就向治理窗报告无活可领，不要自建任务面、也不要重复建已在池里的同类任务"
        "（create_task 撞查重时会静默返回同键的旧件，见队列卡 F05）。"
    )
    return listing


def describe_task_for_worker(task_pool: Any, task_id: str) -> Dict[str, Any]:
    """Read back what the pool actually holds for one task, credentials withheld.

    ``VERIFICATION.method`` tells a worker to 读回任务记录, and the cold handoff
    proved that sentence was not executable: once a submit moves the task to
    ``review`` it disappears from ``list-pending``, so a shell-only worker holds
    nothing but the receipt it just received -- self-attestation, the one thing
    ACE refuses to treat as a fact.  This is the missing read side.

    It is deliberately the *stored* state, not the worker's claim about it: the
    evidence rows, the ledger buckets and the checkpoint tail come off the record
    so a disagreement between "what I submitted" and "what is on disk" is
    visible.  ``claim_id`` and ``fencing_token`` are not returned, because this
    verb needs no authority and printing them would turn a convenience read into
    a credential leak.
    """

    task_id = str(task_id or "").strip()
    if not task_id:
        return _refusal("capsule_task_id_missing", "", "pass --task-id")
    task = task_pool.load_task(task_id)
    if task is None:
        return _refusal(
            "task_not_found",
            task_id,
            port_prefix(task_pool) + " list-pending",
            pool=pool_face(task_pool),
            meaning="这个 id 在本池的任何状态桶里都不存在：不是你领到的那件",
        )

    envelope = _envelope_of(task)
    ledger = envelope.get("evidence_ledger") or {}
    checkpoints = envelope.get("checkpoints") or []
    tail = checkpoints[-_MAX_CHECKPOINTS_SHOWN:] if isinstance(checkpoints, list) else []
    evidence_rows = [row for row in (getattr(task, "evidence", None) or []) if isinstance(row, dict)]
    lease_state, seconds_remaining = _lease_state(task)
    owned = str(getattr(task, "lease_owner", "") or "")

    return {
        "status": "TASK_SEEN",
        "task_id": str(getattr(task, "task_id", "")),
        "pool": pool_face(task_pool),
        "stored_status": str(getattr(task, "status", "")),
        "title": _one_line(getattr(task, "title", ""), 160),
        "retry_count": int(getattr(task, "retry_count", 0) or 0),
        "lease": {
            "state": lease_state,
            "owner": owned,
            "expires_at": _one_line(getattr(task, "lease_expires_at", ""), 40),
            "seconds_remaining": round(seconds_remaining, 3) if seconds_remaining is not None else None,
            "note": "claim_id/fencing_token 不在这里返回：本命令只读，不需要凭证",
        },
        "result_summary": _one_line(getattr(task, "result", "") or "", 400),
        "evidence_rows": [
            {
                "content": _one_line(row.get("content", ""), 200),
                "source": _one_line(row.get("source", ""), 120),
                "added_at": _one_line(row.get("added_at", ""), 40),
            }
            for row in evidence_rows[-_MAX_CHECKPOINTS_SHOWN:]
        ],
        "evidence_total": len(evidence_rows),
        "ledger_counts": {
            kind: len(list((ledger.get(kind) or []) if isinstance(ledger, dict) else []))
            for kind in ("source", "runtime", "result", "review", "unknown")
        },
        "checkpoints_tail": [
            {
                "name": _one_line(row.get("name", ""), 60),
                "status": _one_line(row.get("status", ""), 40),
                "actor": _one_line(row.get("actor", ""), 60),
                "at": _one_line(row.get("at", row.get("recorded_at", "")), 40),
                # which brief the hand-back proved itself against, or null when the
                # worker submitted without ever rendering -- the difference between
                # "carried by the capsule" and "guessed its way in" is exactly what a
                # reviewer has to be able to see from the record alone.
                "capsule_hash": _one_line(row.get("capsule_hash", "") or "", 64) or None,
                "evidence_count": row.get("evidence_count"),
            }
            for row in tail
            if isinstance(row, dict)
        ],
        "checkpoints_omitted": max(0, (len(checkpoints) if isinstance(checkpoints, list) else 0) - len(tail)),
        "next_step": (
            "这条任务还在你名下：跑 renew 续租，或按胶囊 RETURN PROTOCOL 交回"
            if str(getattr(task, "status", "")) == "active" and owned
            else "已离开 active：本轮交回已落盘，用 list-pending 找下一件活"
        ),
        "runtime_mutation": False,
    }


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


def _fact_line(item: Any) -> str:
    """Render one admitted item as a sentence that carries where it came from.

    ``admission.evidence`` rows are ``{content, source}`` dicts, and the first
    version of the capsule printed them with ``json.dumps``: a worker read a
    ``- {"content": "...", "source": "field-scan"}`` line as payload-shaped
    noise instead of a claim it could go and re-check.  The source is the whole
    point of an admitted fact, so it stays visible as a pointer rather than a
    JSON key.
    """

    if isinstance(item, dict):
        content = _one_line(item.get("content") or item.get("fact") or item.get("summary") or "")
        source = _one_line(item.get("source") or item.get("from") or "")
        if content and source:
            return f"{content}  (依据: {source})"
        if content:
            return content
        leftover = _one_line(item)
        if leftover and leftover not in ("{}", "null"):
            return leftover
        return ""
    return _one_line(item)


def _section_lines(items: List[Any]) -> Tuple[List[str], int]:
    lines: List[str] = []
    for item in items:
        rendered = _fact_line(item)
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
    if not isinstance(outputs, dict):
        return {}
    envelope = outputs.get("execution_discipline")
    if isinstance(envelope, ExecutionDiscipline):
        return envelope.to_dict()
    if isinstance(envelope, dict):
        return envelope
    return {}


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
                    port_prefix(task_pool)
                    + f" render --task-id {getattr(task, 'task_id', '')} "
                    + f"--claim {stored_claim} --token {int(getattr(task, 'fencing_token', 0) or 0)}"
                ),
            }
        )

    if rows:
        hint = "re-render with the next_command above -- do NOT call start again, it will refuse a live lease"
    else:
        hint = "no live lease held by this owner; run list-pending and start a task"
        if expired:
            hint = (
                "the lease is expired, not lost: reclaim your own task with "
                "'reclaim --task-id 【任务id】 --actor 【你的worker名】', then start that task again"
            )
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


def reclaim_own_expired_lease(
    task_pool: Any,
    task_id: str,
    *,
    actor: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Close the limbo window for ONE task: its owner returns after the lease died.

    Between lease expiry and the next scheduler-side ``reclaim_stale_leases`` pass
    the record is neither writable by its dead owner nor claimable by anyone else.
    The drill documents that window; nothing on the shell port could shorten it, so
    a weak worker's own recovery hint told it to "run TaskPool.reclaim_stale_leases"
    -- Python it cannot execute.

    This is deliberately NOT that call.  ``reclaim_stale_leases`` sweeps every
    expired lease in the pool, which is a scheduler's authority, not a worker's.
    Here exactly one task moves, and only if the caller is the recorded
    ``lease_owner`` of that task and that lease is no longer live; the move goes
    through ``TaskPool.move_task`` with the caller's own stored claim, so the pool's
    transition table and lease clearing stay the single source of the rule.

    Writes the pool (``runtime_mutation`` True) only on the accepted path.
    """

    if not isinstance(task_id, str) or not task_id.strip():
        return _refusal("capsule_task_id_missing", task_id or "", "reclaim needs the task id shown by recover")
    task_id = task_id.strip()
    if not isinstance(actor, str) or not actor.strip():
        return _refusal("capsule_actor_missing", task_id, "reclaim needs the same --owner name the lease was taken under")
    actor = actor.strip()

    task = task_pool.load_task(task_id)
    if task is None:
        return _refusal("task_not_found", task_id, "the task record is not in any pool bucket")

    status = str(getattr(task, "status", ""))
    if status != "active":
        return _refusal(f"capsule_task_not_active:{status}", task_id, "only an active (leased) record can be reclaimed")

    stored_claim = str(getattr(task, "claim_id", "") or "")
    if not stored_claim:
        return _refusal(
            "capsule_unleased_active_record",
            task_id,
            "an active record with no claim is the scheduler's orphan case, not a worker's own lease",
        )
    if str(getattr(task, "lease_owner", "") or "") != actor:
        # Never echo the holder's claim id: this port must not become a way to
        # take over someone else's task.
        return _refusal(
            "capsule_not_lease_owner",
            task_id,
            f"this lease belongs to another owner; use recover --owner {actor} to find your own",
        )

    lease, seconds_remaining = _lease_state(task, now)
    if lease == "leased":
        return _refusal(
            "capsule_lease_still_live",
            task_id,
            "your lease is still live: keep working, or renew instead of reclaiming",
            lease_seconds_remaining=round(seconds_remaining, 3) if seconds_remaining is not None else None,
            lease_expires_at=_one_line(getattr(task, "lease_expires_at", ""), 40),
        )

    previous_token = int(getattr(task, "fencing_token", 0) or 0)
    moved = task_pool.move_task(
        task_id,
        "pending",
        actor=actor,
        reason=f"capsule_self_reclaim:{stored_claim}",
        claim_id=stored_claim,
    )
    if moved is None:
        return _refusal(
            "capsule_reclaim_refused_by_pool",
            task_id,
            "the pool rejected the move (transition table or claim raced); re-read the record",
            lease_state=lease,
        )

    return {
        "status": "LEASE_RECLAIMED",
        "task_id": task_id,
        "actor": actor,
        "lease_state_at_reclaim": lease,
        "previous_claim_id": stored_claim,
        "previous_fencing_token": previous_token,
        "stored_status": moved.status,
        "next_command": port_prefix(task_pool) + f" start --task-id {task_id} --owner {actor}",
        "runtime_mutation": True,
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
    seen_known: set[tuple[str, str]] = set()
    for item in known:
        if isinstance(item, dict):
            content = _one_line(item.get("content") or item.get("fact") or item.get("summary") or "")
            source = _one_line(item.get("source") or item.get("from") or "")
        else:
            content = _one_line(item)
            source = ""
        key = (content, source)
        if content and key not in seen_known:
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
    lines.append("- read_back: 用 RETURN PROTOCOL 里「交回后自检」那条命令，能看到这条任务真的落在哪个状态")
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

    # Everything below this line is port face, not project content: it is what
    # tells the worker how to hand the task back alive.  A fat envelope must
    # therefore cost the worker some known-facts, never the way out — so the
    # budget is applied to the head only and this tail is reserved.  The tail is
    # itself ordered commands-first, because a starved budget keeps its front.
    protocol_start = len(lines)

    lines.append(
        "== RETURN PROTOCOL (shell 端口，照抄即可，不必写 Python；"
        "命令形状与解释器口径见队列 PROTOCOL 的 C-12 第 10 款，本胶囊只指向不复述) =="
    )
    lines.extend(
        _return_protocol_lines(
            task_pool,
            task_id,
            str(authority["claim_id"]),
            int(authority["fencing_token"]),
            str(getattr(task, "lease_owner", "") or ""),
        )
    )

    lines.append("== RESULT PAYLOAD (submit 的 --payload-file 只准这些键) ==")
    lines.extend(_submit_payload_lines())

    # Last inside the reserved block on purpose: when even the budget cannot hold
    # the port face the tail is kept from its front, so the commands survive and
    # this prose is what goes.  These four lines also live in the task record.
    lines.append("== FORBIDDEN ==")
    forbidden = list(ng_lines) + [f"- {row}" for row in _PORT_FORBIDDEN]
    lines.extend(forbidden)

    lines.append("== STOP ==")
    for condition in list(stop.get("conditions") or []):
        lines.append(f"- {_one_line(condition)}")

    total_lines = len(lines)
    head_lines, tail_lines = lines[:protocol_start], lines[protocol_start:]
    tail_text = "\n".join(tail_lines)
    suffix = "\n[TRUNCATED_BY_BUDGET — 原文超出胶囊预算，未截断的信息仍完整保存在 task 记录里]"
    body = "\n".join(lines)
    if len(body) > char_budget:
        if len(tail_text) + len(suffix) + 1 <= char_budget:
            keep = char_budget - len(suffix) - len(tail_text) - 1
            body = "\n".join(head_lines)[:keep] + suffix + "\n" + tail_text
        else:
            # The budget cannot carry both faces, so the way back wins: a capsule
            # without a return protocol cannot be handed back at all, whereas one
            # that lost some known-facts still can.  Reported, never silent.
            marker = suffix.strip()
            body = marker + "\n" + tail_text[: max(0, char_budget - len(marker) - 1)]
            omitted["port_face_pressure"] = omitted.get("port_face_pressure", 0) + 1
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
        # The minimum budget that still carries the whole port face; below it the
        # caller is choosing to drop the way back, so say so instead of letting
        # them discover it from a garbled capsule.
        "protocol_floor_chars": len(tail_text) + len(suffix) + 1,
        "line_count": body.count("\n") + 1,
        "line_count_total": total_lines,
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
        # How many rows arrived as bare strings and were stamped ``worker-stated``:
        # self-attestation, not a pointer.  A reviewer must be able to see that
        # count on the receipt, and the capsule must not promise it was refused.
        "self_stated_evidence": sum(1 for row in evidence_rows if row["source"] == "worker-stated"),
        "facts_count": len(facts),
        "unknowns_count": len(unknowns),
        "objections_count": len(objections),
        "checkpoint_name": checkpoint_name,
        "capsule_hash": str(seen_capsule_hash) if isinstance(seen_capsule_hash, str) and seen_capsule_hash else None,
        "transition": transition or None,
        "stored_status": getattr(moved, "status", None) if moved is not None else "active",
        "continuation": _continuation(task_pool, actor),
        "runtime_mutation": True,
    }
