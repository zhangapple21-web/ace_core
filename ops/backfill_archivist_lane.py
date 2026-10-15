"""Backfill the 9 records the archivist wrote before it could name itself.

Attribution is established from the task records, not from an assumption: all
nine were archived by an `archivist:transition` audit entry and every one carries
a `learning_return` output, which is the code path that calls
`_deposit_archived_experience` -> `deposit_from_task`. That is the evidence for
naming the daemon-archivist here.

The 1125 August-September records are deliberately not touched. There is no
audit trail tying them to a window, and inventing one would be the same defect
this work removes, wearing the opposite hat.
"""
import json
import os
from pathlib import Path

ROOT = Path(r"C:\tmp/ace_core")
KNOWLEDGE = ROOT / "09_KNOWLEDGE"
LANE = "daemon-archivist"
AUDIT_ACTOR = "archivist"
DAY = "2026-10-15"


def _archived_by_archivist(task_id: str) -> bool:
    for status in ("archived", "graveyard", "blocked"):
        path = ROOT / "task_pool" / status / f"{task_id}.json"
        if not path.is_file():
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(record, dict):
            continue
        outputs = record.get("outputs") or {}
        for entry in record.get("audit_log") or []:
            if isinstance(entry, dict) and entry.get("actor") == AUDIT_ACTOR:
                # learning_return is written by the same call that deposits, so
                # its presence ties the audit entry to this deposit path
                return bool(outputs.get("learning_return"))
    return False


def main(apply: bool = False) -> dict:
    labelled, skipped, unproven = [], [], []
    for path in sorted((KNOWLEDGE / "pattern").glob("EXP-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("depositing_lane"):
            continue
        if str(data.get("created_at", ""))[:10] != DAY:
            skipped.append(path.name)
            continue
        source = str(data.get("source_task_id") or "")
        if not source or not _archived_by_archivist(source):
            # Named, not silently skipped: an unproven record stays unattributed
            unproven.append(source)
            continue
        if apply:
            data["depositing_lane"] = LANE
            temporary = path.with_suffix(".json.tmp")
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        labelled.append(source)

    return {
        "apply": apply,
        "labelled": len(labelled),
        "labelled_ids": labelled,
        "left_unattributed_other_days": len(skipped),
        "left_unattributed_no_proof": unproven,
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(main("--apply" in sys.argv), ensure_ascii=False, indent=2))
