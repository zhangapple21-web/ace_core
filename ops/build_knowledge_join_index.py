"""Rebuild 09_KNOWLEDGE/join_index.v1.json from the authoritative stores.

The reader (`core/knowledge_reuse.py`) trusts this file completely: if it is
missing, stale, or names artifacts that do not exist, the reuse stage silently
plans nothing.  Nothing in the tree builds it, so it has been frozen at
2026-10-03T20:57 and points only at records that predate the epistemic merge —
which is why no real task can match graded knowledge today.

This rebuilds it from the two things that ARE authoritative:

  * ``09_KNOWLEDGE/index.json`` + the per-record files, for what knowledge exists
  * ``task_pool/archived``, for which archived task owns which record

It only reads. It writes the index atomically. It never promotes, grades or
deletes anything.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge_reuse import INDEX_PROTOCOL  # noqa: E402
from core.task import TaskPool  # noqa: E402

KNOWLEDGE = ROOT / "09_KNOWLEDGE"
INDEX_PATH = KNOWLEDGE / "join_index.v1.json"
KNOWLEDGE_INDEX = KNOWLEDGE / "index.json"
POOL = TaskPool(str(ROOT / "task_pool"))


def _load_index() -> Dict[str, Any]:
    if not KNOWLEDGE_INDEX.exists():
        return {}
    try:
        value = json.loads(KNOWLEDGE_INDEX.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _record_from_path(path_text: str) -> Dict[str, Any] | None:
    path = Path(path_text)
    if not path.is_absolute():
        path = KNOWLEDGE / path_text
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "experience_id": str(payload.get("experience_id") or path.stem),
        "source_task_id": str(payload.get("source_task_id") or ""),
        "experience_type": str(payload.get("experience_type") or ""),
        # Absent on pre-merge records. Grade is derived from experience_type so a
        # reader can still tell a RULE from an OBSERVATION without a rewrite.
        "epistemic_status": str(
            payload.get("epistemic_status")
            or {"axiom": "VERIFIED_FACT", "constraint": "RULE",
                "pattern": "EVIDENCE", "lesson": "COUNTEREXAMPLE",
                "observation": "OBSERVATION"}.get(
                    str(payload.get("experience_type") or ""), "UNKNOWN")
        ),
        # Posix separators: the reader joins these onto a workspace root, and a
        # native backslash form makes the index non-portable across machines.
        "path": path.as_posix(),
    }


def build() -> Dict[str, Any]:
    knowledge_index = _load_index()

    by_task: Dict[str, Dict[str, List[str]]] = {}
    by_experience: Dict[str, List[str]] = {}
    dangling: List[Dict[str, str]] = []
    graded = {"RULE": 0, "VERIFIED_FACT": 0, "EVIDENCE": 0,
              "COUNTEREXAMPLE": 0, "OBSERVATION": 0, "UNKNOWN": 0}

    for experience_id, entry in knowledge_index.items():
        if not isinstance(entry, dict):
            continue
        record = _record_from_path(str(entry.get("path", "")))
        if record is None:
            dangling.append({"id": str(experience_id),
                             "reason": "path_missing_or_unreadable"})
            continue
        graded[record["epistemic_status"]] = \
            graded.get(record["epistemic_status"], 0) + 1
        source_task = record["source_task_id"]
        if not source_task:
            continue
        slot = by_task.setdefault(source_task, {"patterns": [], "cards": []})
        slot["patterns"].append(record["path"])
        by_experience.setdefault(record["experience_id"], []).append(record["path"])

    # Keep only tasks that are genuinely archived: the reader joins on the
    # archive, and pointing at a live task would invite reuse of work in flight.
    archived_ids = {t.task_id for t in POOL.list_tasks(status="archived", limit=100000)}
    live_only = [tid for tid in by_task if tid not in archived_ids]
    for task_id in live_only:
        by_task.pop(task_id, None)
    for experience_id, paths in list(by_experience.items()):
        if all(not any(p in paths for p in slot["patterns"])
               for slot in by_task.values()):
            by_experience.pop(experience_id, None)

    for slot in by_task.values():
        slot["patterns"] = sorted(set(slot["patterns"]))

    return {
        "protocol": INDEX_PROTOCOL,
        "built_at": datetime.now().isoformat(),
        "source": "ops/build_knowledge_join_index.py",
        "endpoints": {
            "knowledge_records": len(knowledge_index),
            "indexed_records": sum(len(s["patterns"]) for s in by_task.values()),
            "archived_tasks": len(by_task),
            "dropped_not_archived": len(live_only),
            "dangling": len(dangling),
            "by_epistemic_status": graded,
        },
        "by_task": by_task,
        "by_experience": by_experience,
        "dangling": dangling,
    }


def main() -> int:
    payload = build()
    temporary = INDEX_PATH.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, INDEX_PATH)

    endpoints = payload["endpoints"]
    print("knowledge_join index rebuilt:", INDEX_PATH)
    print(f"  knowledge records known : {endpoints['knowledge_records']}")
    print(f"  indexed records        : {endpoints['indexed_records']}")
    print(f"  archived tasks indexed : {endpoints['archived_tasks']}")
    print(f"  dropped (not archived) : {endpoints['dropped_not_archived']}")
    print(f"  dangling               : {endpoints['dangling']}")
    for status, count in endpoints["by_epistemic_status"].items():
        if count:
            print(f"    {status:15} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())