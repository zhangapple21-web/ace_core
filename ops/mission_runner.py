"""Mission runner for STATE_CALCULUS_LONG_TERM_EVOLUTION.

Deliberately NOT a daemon and NOT an infinite loop. One invocation = one bounded
round. This is the same discipline the existing loop already uses ("自主执行必须
带超时和健康检查，不能无限循环"), and it is what keeps a Mission from becoming one
ungovernable Task.

Caveat, recorded because the first version of this docstring asserted the opposite
and was wrong: nothing invokes this file. A repository-wide search on 2026-10-05
(excluding .git/.venv/__pycache__/backups) found zero references to
`mission_runner` outside its own definition, and the Heartbeat self-loop listed in
AGENTS.md does not include it. It is therefore an ON-DEMAND tool:

    python ops/mission_runner.py

Wiring it into Heartbeat is a production governance change and is out of scope for
the mission that authored it. Do not read "runs successfully" as "runs
automatically". `_slice.py`, `_bisect.py` and `_percase.py` beside this file are
on-demand test-attribution helpers with the same property: they exist because a
full-suite run could not otherwise be attributed, not because anything calls them.

Round shape:

    observe  -> read live TaskPool state, do not mutate
    judge    -> classify each candidate task against the growth rule
    dispatch -> claim at most N tasks, render their capsules to disk
    collect  -> read back worker/verifier artifacts if present
    record   -> append one durable evidence record per round
    stop     -> always terminate with a machine-readable summary

It never submits on a worker's behalf and never writes a terminal state. Those
stay with the worker capsule path so that fencing and validation still apply.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(ACE_ROOT, "task_pool")
MISSION = "STATE_CALCULUS_LONG_TERM_EVOLUTION"
EVIDENCE_DIR = os.path.join(ACE_ROOT, "09_KNOWLEDGE", "mission_rounds")
CAPSULE_DIR = os.path.join(ACE_ROOT, "06_RUNTIME", "ace", "data", "mission_capsules")
OWNER = "steward_window_A"
MAX_DISPATCH = 2

sys.path.insert(0, ACE_ROOT)

from core.task import TaskPool, execution_gate  # noqa: E402
from core import execution_discipline as ed  # noqa: E402


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def mission_tasks(pool: TaskPool) -> list:
    tag = "mission:%s" % MISSION
    out = []
    for status in ("pending", "active", "review", "blocked"):
        for task in pool.list_tasks(status=status, limit=10000):
            if tag in (task.tags or []) or task.parent_task:
                out.append(task)
    seen, uniq = set(), []
    for t in sorted(out, key=lambda x: x.created_at or ""):
        if t.task_id not in seen:
            seen.add(t.task_id)
            uniq.append(t)
    return uniq


def envelope_health(task) -> dict:
    try:
        result = ed.validate_execution_discipline(task)
        return {
            "valid": bool(result.get("valid")),
            "errors": list(result.get("errors") or []),
            "status": result.get("status"),
        }
    except Exception as exc:  # pragma: no cover
        return {"valid": None, "errors": ["validator_raised:%r" % (exc,)], "status": None}


def judge(task) -> dict:
    """Classify one task against the Mission growth rule. No mutation."""
    disc = (task.outputs or {}).get("execution_discipline") or {}
    env = envelope_health(task)
    reasons = []
    if task.status in ("pending", "active"):
        ready, why = execution_gate(task, allow_backfill=False)
        if not ready:
            reasons.append("gate_not_ready:%s" % why)
    if env["errors"]:
        reasons.append("envelope:%s" % ",".join(env["errors"][:3]))
    blockers = [r for r in reasons if r.startswith(("gate_not_ready", "envelope"))]
    if blockers:
        disposition = "BLOCKED_BY_PLATFORM"
        next_step = "escalate_or_fix_platform_before_dispatch"
    elif task.status == "pending":
        disposition = "READY_TO_DISPATCH"
        next_step = "claim_and_render"
    elif task.status == "active":
        disposition = "IN_FLIGHT"
        next_step = "await_worker_or_reclaim_expired_lease"
    elif task.status == "review":
        disposition = "AWAITING_VALIDATOR"
        next_step = "await_validator_or_guardian"
    else:
        disposition = "TERMINAL_OR_BLOCKED"
        next_step = "read_blocked_reason_and_decide"
    return {
        "task_id": task.task_id,
        "status": task.status,
        "title": task.title,
        "disposition": disposition,
        "next_step": next_step,
        "reasons": reasons,
        "envelope": env,
        "complexity": disc.get("complexity"),
        "evidence_count": len(task.evidence or []),
    }


def render_capsule(task_id: str, claim: str, token: int) -> dict:
    os.makedirs(CAPSULE_DIR, exist_ok=True)
    dest = os.path.join(CAPSULE_DIR, "%s.json" % task_id)
    proc = subprocess.run(
        [sys.executable, "-m", "ops.worker_capsule_cli", "--pool", POOL,
         "render", "--task-id", task_id, "--claim", claim, "--token", str(token)],
        cwd=ACE_ROOT, capture_output=True, timeout=120,
    )
    # The CLI emits UTF-8 JSON regardless of the host locale. Decoding with the
    # console code page raises UnicodeDecodeError on Chinese payloads and would
    # otherwise be misread as a render failure.
    stdout = (proc.stdout or b"").decode("utf-8", "replace")
    stderr = (proc.stderr or b"").decode("utf-8", "replace")
    payload = {"task_id": task_id, "render_ok": proc.returncode == 0,
               "returncode": proc.returncode}
    try:
        payload["capsule"] = json.loads(stdout.strip().splitlines()[-1])
    except Exception:
        payload["stdout"] = stdout[:500]
        payload["stderr"] = stderr[-500:]
    with io.open(dest, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=1))
    payload["path"] = dest
    return payload


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    pool = TaskPool(POOL)
    tasks = mission_tasks(pool)

    judged = [judge(t) for t in tasks]
    ready = [j for j in judged if j["disposition"] == "READY_TO_DISPATCH"]

    dispatched = []
    for j in ready[:MAX_DISPATCH]:
        task = pool.load_task(j["task_id"])
        claimed = pool.claim_task(task.task_id, OWNER, lease_seconds=3600)
        if not claimed:
            dispatched.append({"task_id": j["task_id"], "claimed": False,
                               "note": "claim refused (lease/retry/gate); not forced"})
            continue
        cap = render_capsule(task.task_id, claimed.claim_id, claimed.fencing_token)
        dispatched.append({
            "task_id": task.task_id,
            "claimed": True,
            "claim_id": claimed.claim_id,
            "fencing_token": claimed.fencing_token,
            "lease_expires_at": claimed.lease_expires_at,
            "capsule_path": cap.get("path"),
            "render_ok": cap.get("render_ok"),
        })

    os.makedirs(EVIDENCE_DIR, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record = {
        "protocol": "ace.mission_round.v1",
        "mission": MISSION,
        "round_started": started,
        "round_finished": datetime.now(timezone.utc).isoformat(),
        "pool_path": POOL,
        "owner": OWNER,
        "max_dispatch": MAX_DISPATCH,
        "observed": {
            "mission_task_count": len(tasks),
            "dispositions": {k: sum(1 for j in judged if j["disposition"] == k)
                             for k in sorted({j["disposition"] for j in judged})},
        },
        "judged": judged,
        "dispatched": dispatched,
        "note": "one bounded round; no infinite loop; no terminal state written",
    }
    path = os.path.join(EVIDENCE_DIR, "round_%s.json" % stamp)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, indent=1))

    print(json.dumps({
        "status": "ROUND_COMPLETE",
        "mission": MISSION,
        "mission_tasks": len(tasks),
        "dispositions": record["observed"]["dispositions"],
        "dispatched": [d["task_id"] for d in dispatched],
        "evidence": path,
        "evidence_sha": sha(path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
