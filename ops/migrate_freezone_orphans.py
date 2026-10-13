"""Migrate free-zone relay orphans into the pool that is actually served.

`ace_daemon` handed FreeZoneReflectionRelay the isolated ``task_pool_freezone``
TaskPool. That pool has no lifecycle: no Researcher claims from it, no Validator
reviews it, no Archivist moves it. The relay therefore became a black hole - 67
verification tasks written into pending and never touched again, while the work
they represent (free-zone results that may contain ACE-verifiable leads) went
nowhere.

The main pool is where the lifecycle lives: it already holds 16 tasks by this
same creator, most of them archived, so the relay used to be wired there. The
isolation intent is preserved by the admission metadata - production_integration
False, next gate is the existing ACE Admission - not by an unserved pool.

This migration is idempotent: a task whose source_ref already exists in the
main pool (in any live state, plus archived history) is skipped, so repeated
runs cannot manufacture a task storm. The freezone copies are left in place and
marked migrated rather than deleted - Archive, do not delete.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(r"C:\tmp\ace_core")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ops"))

from core.task import TaskPool  # noqa: E402

FZ_PENDING = ROOT / "task_pool_freezone" / "pending"
MAIN = ROOT / "task_pool"


def source_ref_of(task: dict) -> str:
    """The dedup key lives in outputs.admission for relay tasks."""
    outputs = task.get("outputs") or {}
    for holder in (outputs.get("admission"), task.get("admission")):
        if isinstance(holder, dict) and str(holder.get("source_ref") or "").strip():
            return str(holder["source_ref"]).strip()
    return ""


def main(apply: bool = False) -> None:
    main_pool = TaskPool(str(MAIN))
    existing_refs: set[str] = set()
    for task in main_pool.list_tasks(limit=10000, sort_by="created"):
        ref = source_ref_of(task.to_dict())
        if ref:
            existing_refs.add(ref)

    orphans = []
    for path in sorted(FZ_PENDING.glob("*.json"), key=lambda p: p.stat().st_mtime):
        task = json.loads(path.read_text(encoding="utf-8"))
        ref = source_ref_of(task)
        if not ref:
            continue
        orphans.append((path, task, ref))

    migrated = skipped = 0
    for path, task, ref in orphans:
        if ref in existing_refs:
            skipped += 1
            continue
        if apply:
            admission = (task.get("outputs") or {}).get("admission") or {}
            created = main_pool.create_task(
                title=str(task.get("title") or "回看自由区结果"),
                hypothesis=str(task.get("hypothesis") or ""),
                creator=str(task.get("creator") or "free_zone_reflection_relay"),
                priority=str(task.get("priority") or "medium"),
                tags=list(task.get("tags") or []),
                depends_on=list(task.get("depends_on") or []),
                parent_task=str(task.get("parent_task") or ""),
                data_class=str(task.get("data_class") or "PRIVATE"),
                admission=admission,
                outputs={
                    "admission": admission,
                    "free_zone_reflection": (task.get("outputs") or {}).get("free_zone_reflection"),
                    "migrated_from": {
                        "pool": "task_pool_freezone",
                        "task_id": task.get("task_id"),
                        "source_ref": ref,
                        "reason": "relay was wired to a pool with no lifecycle",
                    },
                },
            )
            if getattr(created, "task_id", ""):
                migrated += 1
                existing_refs.add(ref)
                # archive the orphan in place: superseded, never deleted
                task["archived_reason"] = "migrated to task_pool/%s" % created.task_id
                task["status"] = "archived"
                path.write_text(json.dumps(task, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        else:
            migrated += 1

    print(json.dumps({
        "apply": apply,
        "orphans_with_source_ref": len(orphans),
        "already_in_main_pool": skipped,
        "migrated_or_would_migrate": migrated,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)