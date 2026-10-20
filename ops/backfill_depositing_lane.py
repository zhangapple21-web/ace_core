"""Backfill: the 67 tombstoning lessons written before depositing_lane existed.

Every one of them hit deposit()'s early-return branch, which at the time returned
the stored record untouched - so the lane was dropped. The records themselves are
correct and must not be rewritten; only the absent attribution is filled.

Idempotent, and it never touches a record that already carries a lane.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(r"C:\tmp/ace_core")
KNOWLEDGE = ROOT / "09_KNOWLEDGE"
AUDIT_ACTOR = "blocked_backlog_disposition"


def _task_origin(task_id: str) -> str | None:
    """Which window disposed this task, read from its persisted record.

    The lesson file does not say who wrote it - that is the gap being filled -
    so the answer has to come from the task the lesson was derived from. Two
    independent signals are accepted: a marker in the task's outputs, or the
    actor that logged the disposition. Reading it from the task rather than
    assuming keeps the backfill honest about what actually happened.
    """
    for status_dir in ("graveyard", "archived", "blocked"):
        path = ROOT / "task_pool" / status_dir / f"{task_id}.json"
        if not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        outputs = record.get("outputs")
        if isinstance(outputs, Mapping) and outputs.get("disposition_contract"):
            return "tombstoning"
        for entry in record.get("audit_log") or []:
            if isinstance(entry, dict) and entry.get("actor") == AUDIT_ACTOR:
                return "tombstoning"
    return None


def main(apply: bool = False) -> dict[str, Any]:
    updated, already, unmatched = [], [], []
    for sub in sorted(KNOWLEDGE.iterdir()):
        if not sub.is_dir():
            continue
        for path in sorted(sub.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            if data.get("depositing_lane"):
                already.append(path.name)
                continue
            source = str(data.get("source_task_id") or "")
            if not source or not source.startswith("RQ-"):
                continue
            lane = _task_origin(source)
            if lane != "tombstoning":
                # Named, not silently skipped: a lesson whose origin cannot be
                # established stays unattributed, and that is a fact worth
                # counting rather than a case to paper over.
                unmatched.append(source)
                continue
            if apply:
                data["depositing_lane"] = lane
                temporary = path.with_suffix(".json.tmp")
                with open(temporary, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            updated.append((source, path.name))

    return {
        "apply": apply,
        "labelled": len(updated),
        "already_labelled": len(already),
        "unmatched_origin": len(unmatched),
        "first_10": [u[0] for u in updated[:10]],
    }


if __name__ == "__main__":
    print(json.dumps(main(apply="--apply" in sys.argv), ensure_ascii=False, indent=2))
