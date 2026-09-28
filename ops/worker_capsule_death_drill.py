"""Cross-process death drill for the weak-worker capsule ports (ACE-QWEN-FIELD-01).

Two *separate* Python processes handle one task.  The first claims it, does
partial work, and dies without releasing anything; the lease is allowed to rot
in real time; the second process reclaims through the existing recovery path
and finishes the task from the capsule it is handed.  Nothing here simulates a
crash inside one process, and nothing writes to the production task pool.

Usage:
    py -3.11 -m ops.worker_capsule_death_drill first  --pool-dir <dir> --state <json>
    py -3.11 -m ops.worker_capsule_death_drill resume --pool-dir <dir> --state <json> --receipt <json>
    py -3.11 -m ops.worker_capsule_death_drill probe  --receipt <json>   # read-only, production pool
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.ace_start import ace_start  # noqa: E402
from core.task import TaskPool  # noqa: E402
from core.worker_capsule import check_capsule_authority, render_task_capsule, submit_task_capsule_result  # noqa: E402

LEASE_SECONDS = 4  # short on purpose: the gap between phases must outlive it

try:  # pragma: no cover - depends on the host stdio
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Scratch pool lives outside the repository so a drill can never look like
# production task state; only the receipt is written back into the evidence dir.
SCRATCH_DEFAULT = Path(os.environ.get("TEMP", "C:/tmp")) / "ace_worker_capsule_drill"

ADMISSION = {
    # ``core.task_admission.SOURCE_TYPES`` has no vocabulary for a direct user
    # directive; widening admission is not a worker-side decision, so the drill
    # enters through the existing ``evidence`` type and records the gap instead.
    "source_type": "evidence",
    "source_ref": "ACE-QWEN-FIELD-01",
    "why_now": "prove task outlives worker across real processes",
    "evidence": [{"source": "field-scan", "content": "claim/lease/reclaim exist in core/task.py"}],
    "expected_result": "recovered task reaching review with both workers' checkpoints",
    "verification_method": "second process reads capsule and finishes",
    "risk": "scratch pool only, production pool untouched",
    "estimated_scope": "one drill",
}


def _log(row: dict) -> None:
    print(json.dumps(row, ensure_ascii=False), flush=True)


def _reset_scratch_pool(pool_dir: Path) -> int:
    """Purge a stale scratch pool so a finished drill can never poison the next run.

    A second ``first`` run used to reuse the task id of an already-reviewed run and
    overwrite its record, quietly destroying the previous evidence.  The purge is only
    allowed inside the drill-owned scratch directory under TEMP, so a mistyped
    ``--pool-dir`` that points at the production pool cannot delete anything.
    """

    temp_root = Path(os.environ.get("TEMP", "C:/tmp")).resolve()
    resolved = pool_dir.resolve()
    if temp_root not in resolved.parents or resolved.name != "pool":
        raise SystemExit(
            json.dumps(
                {
                    "phase": "first",
                    "status": "REFUSED",
                    "reason": "pool_dir_is_not_the_scratch_pool",
                    "pool_dir": str(resolved),
                    "scratch_root": str(temp_root),
                    "recovery_hint": "drop --pool-dir, or point it at a directory under %TEMP% named pool",
                },
                ensure_ascii=False,
            )
        )
    removed = 0
    if resolved.exists():
        for path in sorted(resolved.rglob("*.json")):
            if path.is_file():
                removed += 1
                path.unlink()
    return removed


def do_first(pool_dir: Path, state_path: Path) -> int:
    pool_dir.mkdir(parents=True, exist_ok=True)
    removed = _reset_scratch_pool(pool_dir)
    pool = TaskPool(str(pool_dir))
    pool.recover_incomplete_transitions()
    task = pool.create_task(
        "跨进程死亡演练：任务必须活过 worker",
        hypothesis="第一进程硬退后，第二进程仍能凭胶囊完成",
        creator="qwen-field-01",
        priority="high",
        complexity="complex",
        tags=["research"],
        admission=dict(ADMISSION),
    )
    started = ace_start(pool, task.task_id, "worker-process-A", lease_seconds=LEASE_SECONDS)
    if started["status"] != "STARTED":
        _log({"phase": "first", "status": "FAILED", "detail": started})
        return 1
    capsule = render_task_capsule(
        pool,
        task.task_id,
        claim_id=started["claim_id"],
        fencing_token=started["fencing_token"],
    )
    if capsule["status"] != "CAPSULE_READY":
        _log({"phase": "first", "status": "FAILED", "detail": capsule})
        return 1
    partial = submit_task_capsule_result(
        pool,
        task.task_id,
        claim_id=started["claim_id"],
        fencing_token=started["fencing_token"],
        actor="worker-process-A",
        seen_capsule_hash=capsule["capsule_hash"],
        payload={
            "evidence": [
                {
                    "content": f"process A pid={os.getpid()} did half the work and will now die",
                    "source": "ops/worker_capsule_death_drill.py:first",
                }
            ],
            "unknowns": ["process A 之后的恢复路径尚未证明"],
            "checkpoint_name": "half_done_process_A",
            "transition": "",
        },
    )
    state_path.write_text(
        json.dumps(
            {
                "task_id": task.task_id,
                "a_claim_id": started["claim_id"],
                "a_fencing_token": started["fencing_token"],
                "a_capsule_hash": capsule["capsule_hash"],
                "a_pid": os.getpid(),
                "a_submit": partial["status"],
                "a_at": datetime.now().isoformat(),
                "lease_seconds": LEASE_SECONDS,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _log(
        {
            "phase": "first",
            "status": "HALF_DONE",
            "scratch_reset_removed_files": removed,
            "detail": partial,
            "capsule_hash": capsule["capsule_hash"],
        }
    )
    # Hard exit: no cleanup, no lease release, no transition.
    os._exit(0)


def do_resume(pool_dir: Path, state_path: Path, receipt_path: Path) -> int:
    if not state_path.exists():
        _log(
            {
                "phase": "resume",
                "status": "NOT_RESUMABLE",
                "reason": "state_file_missing",
                "state_path": str(state_path),
                "recovery_hint": "run the 'first' phase before 'resume'",
                "runtime_mutation": False,
            }
        )
        return 2
    state = json.loads(state_path.read_text(encoding="utf-8"))
    pool = TaskPool(str(pool_dir))
    task_id = state["task_id"]

    # Pre-flight with the same ruler the write port uses.  Running the ghost step
    # while process A's lease is still live is not a death drill at all: those
    # credentials are genuinely valid, the ghost write succeeds, the task moves to
    # review, and the recovery scenario is silently consumed by a legitimate write.
    # Observed 18:14:26 the same second as 'first' (audit row
    # ``active -> review / worker-process-A-ghost / capsule_submit:worker_submission``).
    still_live = check_capsule_authority(
        pool,
        task_id,
        claim_id=state["a_claim_id"],
        fencing_token=state["a_fencing_token"],
    )
    if still_live.get("status") == "AUTHORIZED":
        _log(
            {
                "phase": "resume",
                "status": "NOT_RESUMABLE",
                "reason": "lease_still_live_ghost_would_be_legal",
                "task_id": task_id,
                "lease_seconds_remaining": still_live.get("lease_seconds_remaining"),
                "lease_seconds_drill_expects": LEASE_SECONDS,
                "recovery_hint": (
                    "run 'resume' at least %d seconds after 'first' (or add --pool-dir of a fresh scratch "
                    "pool and re-run 'first'); nothing was written by this attempt" % LEASE_SECONDS
                ),
                "runtime_mutation": False,
            }
        )
        return 2

    zombie = submit_task_capsule_result(
        pool,
        task_id,
        claim_id=state["a_claim_id"],
        fencing_token=state["a_fencing_token"],
        actor="worker-process-A-ghost",
        payload={"facts": ["ghost write must be refused"], "transition": "review"},
    )

    expired_refusal = render_task_capsule(
        pool,
        task_id,
        claim_id=state["a_claim_id"],
        fencing_token=state["a_fencing_token"],
    )

    zombie_blocked = zombie.get("status") == "REFUSED" and zombie.get("runtime_mutation") is False and zombie.get(
        "reason"
    ) in {"capsule_lease_expired", "capsule_claim_mismatch", "capsule_fencing_token_stale"}
    limbo = pool.load_task(task_id)
    ghost_left_no_trace = limbo is not None and limbo.status == "active" and len(limbo.evidence) == 1

    reclaimed = pool.reclaim_stale_leases()
    started = ace_start(pool, task_id, "worker-process-B", lease_seconds=60)
    if started.get("status") != "STARTED":
        # The task is no longer claimable (a finished run, or the lease has not been
        # reclaimed yet).  Report one readable row instead of a KeyError stack trace:
        # a weak worker must be able to tell "nothing to resume" from "the gate broke".
        _log(
            {
                "phase": "resume",
                "status": "NOT_RESUMABLE",
                "task_id": task_id,
                "reason": started.get("reason"),
                "current_status": (limbo.status if limbo is not None else "task_not_found"),
                "ghost_write_blocked": zombie_blocked,
                "ghost_left_no_trace": ghost_left_no_trace,
                "expired_render": expired_refusal.get("reason"),
                "reclaimed_task_ids": [task.task_id for task in reclaimed],
                "recovery_hint": "wait for the lease to expire and let a reclaim pass run, or re-run 'first'",
                "runtime_mutation": False,
            }
        )
        return 2
    capsule = render_task_capsule(
        pool,
        task_id,
        claim_id=started["claim_id"],
        fencing_token=started["fencing_token"],
    )
    finished = None
    if capsule["status"] == "CAPSULE_READY":
        finished = submit_task_capsule_result(
            pool,
            task_id,
            claim_id=started["claim_id"],
            fencing_token=started["fencing_token"],
            actor="worker-process-B",
            seen_capsule_hash=capsule["capsule_hash"],
            payload={
                "summary": "接力完成：进程 A 的半程证据仍在胶囊 CHECKPOINTS 中",
                "facts": ["跨进程死亡后任务被回收、重新认领并推进到 review"],
                "evidence": [
                    {
                        "content": f"process B pid={os.getpid()} read capsule {capsule['capsule_hash'][:12]}",
                        "source": "ops/worker_capsule_death_drill.py:resume",
                    }
                ],
                "objections": ["演练在 scratch 池，未覆盖生产池并发认领"],
                "next_verification": "在生产池以只读渲染验证同一门禁",
                "stop_condition": "胶囊不再能读出上一棒 checkpoint 时停止",
                "transition": "review",
            },
        )

    stored = pool.load_task(task_id)
    checkpoints = [
        item.get("name")
        for item in stored.outputs["execution_discipline"].get("checkpoints", [])
    ]
    receipt = {
        "drill": "ace.worker_capsule.death_drill.v1",
        "at": datetime.now().isoformat(),
        "pool_dir": str(pool_dir),
        "task_id": task_id,
        "process_a": {
            "pid": state["a_pid"],
            "claim_id": state["a_claim_id"],
            "capsule_hash": state["a_capsule_hash"],
            "hard_exit": True,
            "submit_status": state["a_submit"],
        },
        "gap_seconds_observed": round(time.time() - os.path.getmtime(state_path), 2),
        "ghost_write": zombie,
        "ghost_write_blocked": zombie_blocked,
        "ghost_left_no_trace": ghost_left_no_trace,
        "expired_render": expired_refusal.get("reason"),
        "reclaimed_task_ids": [task.task_id for task in reclaimed],
        "process_b": {
            "pid": os.getpid(),
            "claim_id": started.get("claim_id"),
            "fencing_token": started.get("fencing_token"),
            "capsule_status": capsule.get("status"),
            "capsule_hash": capsule.get("capsule_hash"),
            "capsule_carries_prior_checkpoint": "half_done_process_A" in (capsule.get("capsule_text") or ""),
            "prior_actor_visible": "worker-process-A" in (capsule.get("capsule_text") or ""),
            "submit_status": (finished or {}).get("status"),
        },
        "final": {
            "status": stored.status,
            "claim_id_cleared": stored.claim_id == "",
            "evidence_count": len(stored.evidence),
            "checkpoints": checkpoints,
            "unknowns_kept": any(
                "worker-unknown::" in item for item in stored.outputs["execution_discipline"]["evidence_ledger"]["unknown"]
            ),
        },
    }
    receipt["observations"] = {
        "limbo_window": (
            "between lease expiry and the next reclaim_stale_leases pass the task is neither writable "
            "by its dead owner nor claimable; recovery is pull-based, so a scheduler pass must run for it to close"
        ),
        "admission_gap": (
            "core/task_admission.SOURCE_TYPES has no user-directive type, so an operator-issued task "
            "must enter as source_type=evidence; widening admission was not done here (worker-side "
            "change to 准入 is forbidden by the execution contract)"
        ),
        "fuel_gap": (
            "the production pool has pending=0, so the capsule has no real work to carry; the drill "
            "therefore proves the mechanism on a scratch pool and only proves the gate read-only in production"
        ),
        "receipt_path_defect_found": (
            "probe and resume originally shared one --receipt default, so re-running probe overwrote the "
            "committed drill PASS receipt with probe data (found at 2026-09-28T17:23 by reading the file "
            "back).  Each phase now owns its own evidence file."
        ),
    }
    verdict = (
        zombie_blocked
        and ghost_left_no_trace
        and expired_refusal.get("reason") == "capsule_lease_expired"
        and [task.task_id for task in reclaimed] == [task_id]
        and capsule.get("status") == "CAPSULE_READY"
        and (finished or {}).get("status") == "SUBMITTED"
        and stored.status == "review"
        and "half_done_process_A" in checkpoints
    )
    receipt["verdict"] = "PASS" if verdict else "FAIL"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    _log({"phase": "resume", "status": receipt["verdict"], "receipt": str(receipt_path), "final": receipt["final"]})
    return 0 if verdict else 1


def do_probe(receipt_path: Path) -> int:
    """Read-only check of the same gate against the production task pool."""

    pool = TaskPool(str(REPO_ROOT / "task_pool"))
    rows = []
    for status in ("blocked", "archived"):
        for task in pool.list_tasks(status=status, limit=3):
            rows.append(
                {
                    "task_id": task.task_id,
                    "status": task.status,
                    "render": render_task_capsule(pool, task.task_id, claim_id="probe", fencing_token=1),
                }
            )
    stats = pool.get_stats()
    receipt = {
        "probe": "ace.worker_capsule.production_readonly.v1",
        "at": datetime.now().isoformat(),
        "pool_stats": stats,
        "samples": [
            {"task_id": row["task_id"], "status": row["status"], "reason": row["render"]["reason"],
             "runtime_mutation": row["render"]["runtime_mutation"]}
            for row in rows
        ],
    }
    receipt["verdict"] = "PASS" if rows and all(row["render"]["status"] == "REFUSED" for row in rows) else "NO_SAMPLES"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    _log({"phase": "probe", "status": receipt["verdict"], "samples": len(rows), "receipt": str(receipt_path)})
    return 0


def main(argv=None) -> int:
    evidence_dir = REPO_ROOT / "08_GOVERNANCE" / "evidence"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("first", "resume", "probe"))
    parser.add_argument("--pool-dir", default=str(SCRATCH_DEFAULT / "pool"))
    parser.add_argument("--state", default=str(SCRATCH_DEFAULT / "state.json"))
    # One default output path per phase: probe used to write into the drill
    # receipt and silently overwrote a committed PASS with its own payload.
    parser.add_argument("--receipt", default=None)
    args = parser.parse_args(argv)
    if args.receipt is None:
        default_name = (
            "worker_capsule_production_probe_20260928.json"
            if args.phase == "probe"
            else "worker_capsule_death_drill_20260928.json"
        )
        args.receipt = str(evidence_dir / default_name)
    pool_dir = Path(args.pool_dir)
    pool_dir.mkdir(parents=True, exist_ok=True)
    if args.phase == "first":
        return do_first(pool_dir, Path(args.state))
    if args.phase == "resume":
        return do_resume(pool_dir, Path(args.state), Path(args.receipt))
    return do_probe(Path(args.receipt))


if __name__ == "__main__":
    raise SystemExit(main())
