"""Canonical, bounded ACE task-start entrypoint.

This module is an adapter over the existing TaskPool.  It is not a scheduler,
queue, lease service, or second authority.  A start may only succeed when the
TaskPool's existing admission-backed execution envelope is startable and the
TaskPool can issue the owner/lease/fencing record.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .execution_discipline import execution_gate


def ace_start(task_pool: Any, task_id: str, owner: str, lease_seconds: int = 300,
              regions: Optional[Iterable[str]] = None,
              lane_registry: Optional[Any] = None,
              base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Attempt one fail-closed start and return an audit-friendly result.

    Starting a task and claiming a file region are two axes of one act. TaskPool's
    owner/lease/fencing covers "this task is mine"; WindowLane's claim covers
    "these files are mine". The draft that named the gap found that claiming only
    the first allowed two windows to write source into one checkout with nothing
    able to stop them, so start now takes both.

    A refused lane claim fails the start: starting a task whose file region
    another lane holds would let this window edit a file mid-write.
    """
    task = task_pool.load_task(task_id)
    if task is None:
        return {"status": "REJECTED", "reason": "task_not_found", "task_id": task_id}

    ready, reason = execution_gate(task, allow_backfill=False)
    if not ready:
        return {
            "status": "REJECTED",
            "reason": reason,
            "task_id": task_id,
            "owner": owner,
            "runtime_mutation": False,
        }

    claimed = task_pool.claim_task(task_id, owner, lease_seconds=lease_seconds)
    if claimed is None:
        return {
            "status": "REJECTED",
            "reason": "taskpool_claim_rejected",
            "task_id": task_id,
            "owner": owner,
            "runtime_mutation": False,
        }

    lane_result = None
    declared = [str(r).strip() for r in (regions or []) if str(r).strip()]
    if declared:
        registry = lane_registry
        if registry is None:
            if not base_dir:
                return {
                    "status": "REJECTED",
                    "reason": "lane_registry_or_base_dir_required",
                    "task_id": task_id, "owner": owner,
                }
            from .window_lane import LaneRegistry
            registry = LaneRegistry(base_dir)
        lane_result = _claim_lanes(registry, declared, owner)
        if lane_result.get("status") == "REFUSED":
            return {
                "status": "REJECTED",
                "reason": "lane_claim_refused",
                "lane_detail": lane_result,
                "task_id": task_id,
                "owner": owner,
                "runtime_mutation": True,
                "release_note": (
                    "taskpool_claim stands; the caller must release the task claim "
                    "or let its lease expire - this module does not silently "
                    "un-claim a claim it did not make"
                ),
            }

    return {
        "status": "STARTED",
        "reason": "taskpool_claimed_with_fencing",
        "task_id": task_id,
        "owner": claimed.lease_owner,
        "claim_id": claimed.claim_id,
        "fencing_token": claimed.fencing_token,
        "lease_expires_at": claimed.lease_expires_at,
        "lane_claims": (lane_result or {}).get("claims", []) if lane_result else [],
        "runtime_mutation": True,
    }


def _claim_lanes(registry: Any, regions: list, owner: str):
    """Claim each named region for `owner`, or refuse the whole start.

    Partial success is not offered: half a lane claim is an unclaimed file the
    window still believes it owns. The registry is passed in already built, so
    the caller decides where the OWNERS table comes from.
    """
    claims = []
    for region in regions:
        result = registry.claim(owner, region, actor="ace_start",
                                reason="declared at task start")
        if isinstance(result, dict) and result.get("status") == "REFUSED":
            for held in claims:
                registry.release(held["claim_id"], token=held["fencing_token"],
                                 actor="ace_start")
            return result
        claims.append(result.to_dict() if hasattr(result, "to_dict") else result)
    return {"status": "CLAIMED", "claims": claims}


def run_runtime(base_dir: Any, config: Dict[str, Any], mode: str, **kwargs: Any) -> Any:
    """Canonical adapter for known ACE runtime modes.

    The adapter delegates to the existing ``AceDaemon`` only; it does not own
    a loop or persist lifecycle state of its own.
    """

    from ace_daemon import AceDaemon
    from core.silent_windows import install_daemon_silence

    allowed = {"run", "once", "submit", "daemon_once", "daemon_serve"}
    if mode not in allowed:
        raise ValueError(f"unsupported_ace_start_mode:{mode}")
    if mode in {"run", "once", "daemon_once", "daemon_serve"}:
        install_daemon_silence()
    daemon = AceDaemon(base_dir, config)
    if mode in {"run", "daemon_serve"}:
        return daemon.run_daemon(
            interval_seconds=kwargs.get("interval_seconds", 300),
            max_iterations=kwargs.get("max_iterations", 0),
            force=kwargs.get("force", False),
            dry_run=kwargs.get("dry_run", False),
        )
    if mode == "once" or mode == "daemon_once":
        return daemon.run_once(force=kwargs.get("force", False), dry_run=kwargs.get("dry_run", False))
    title = kwargs.get("title")
    content = kwargs.get("content")
    if not isinstance(title, str) or not title.strip() or not isinstance(content, str):
        raise ValueError("submit_requires_title_and_content")
    observation = daemon.runtime_observer.record(
        description=f"{title}: {content}",
        system_state={"title": title, "content": content},
        source="cli",
        category="manual",
        auto_generated=False,
    )
    return {"observation_id": observation.obs_id, "result": daemon.run_once()}
