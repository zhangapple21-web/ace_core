"""Canonical, bounded ACE task-start entrypoint.

This module is an adapter over the existing TaskPool.  It is not a scheduler,
queue, lease service, or second authority.  A start may only succeed when the
TaskPool's existing admission-backed execution envelope is startable and the
TaskPool can issue the owner/lease/fencing record.
"""

from __future__ import annotations

from typing import Any, Dict

from .execution_discipline import execution_gate


def ace_start(task_pool: Any, task_id: str, owner: str, lease_seconds: int = 300) -> Dict[str, Any]:
    """Attempt one fail-closed start and return an audit-friendly result."""

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
    return {
        "status": "STARTED",
        "reason": "taskpool_claimed_with_fencing",
        "task_id": task_id,
        "owner": claimed.lease_owner,
        "claim_id": claimed.claim_id,
        "fencing_token": claimed.fencing_token,
        "lease_expires_at": claimed.lease_expires_at,
        "runtime_mutation": True,
    }


def run_runtime(base_dir: Any, config: Dict[str, Any], mode: str, **kwargs: Any) -> Any:
    """Canonical adapter for known ACE runtime modes.

    The adapter delegates to the existing ``AceDaemon`` only; it does not own
    a loop or persist lifecycle state of its own.
    """

    from ace_daemon import AceDaemon

    allowed = {"run", "once", "submit", "daemon_once", "daemon_serve"}
    if mode not in allowed:
        raise ValueError(f"unsupported_ace_start_mode:{mode}")
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
