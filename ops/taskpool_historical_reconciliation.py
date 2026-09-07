#!/usr/bin/env python3
"""Produce a read-only TaskPool historical-duplicate reconciliation dry run.

The command never opens a TaskPool mutation API and never writes a report.  Its
JSON output is an auditable proposal only; an eventual apply path must remain a
separate, state-machine-governed change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable


BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_RULES = {"lexicon_category_gap", "recent_errors"}


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _snapshot(pool: Path) -> list[Dict[str, Any]]:
    manifest = []
    for path in sorted(pool.glob("*/*.json")):
        try:
            raw = path.read_bytes()
            record = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        manifest.append({
            "path": str(path),
            "state_dir": path.parent.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "record": record,
        })
    return manifest


def _digest(manifest: Iterable[Dict[str, Any]]) -> str:
    stable = [
        {key: item[key] for key in ("path", "state_dir", "sha256")}
        for item in manifest
    ]
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


def _outputs(record: Dict[str, Any]) -> Dict[str, Any]:
    outputs = record.get("outputs", {})
    return outputs if isinstance(outputs, dict) else {}


def _admission(record: Dict[str, Any]) -> Dict[str, Any]:
    admission = _outputs(record).get("admission", {})
    return admission if isinstance(admission, dict) else {}


def _state(record: Dict[str, Any]) -> Dict[str, Any]:
    evidence = _admission(record).get("evidence", [])
    if not isinstance(evidence, list) or not evidence or not isinstance(evidence[0], dict):
        return {}
    value = evidence[0].get("system_state", {})
    return value if isinstance(value, dict) else {}


def _normal_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ()
    return tuple(sorted({" ".join(str(item).strip().lower().split()) for item in values if str(item).strip()}))


def _signature(record: Dict[str, Any]) -> tuple[str, str] | None:
    rule = str(_outputs(record).get("conversion_rule", ""))
    state = _state(record)
    if rule == "lexicon_category_gap":
        values = _normal_list(state.get("gap_categories"))
        return (rule, "|".join(values)) if values else None
    if rule == "recent_errors":
        values = _normal_list(state.get("error_samples"))
        return (rule, "|".join(values)) if values else None
    return None


def _eligible(item: Dict[str, Any], cutoff: datetime) -> tuple[bool, str]:
    record = item["record"]
    if item["state_dir"] != "pending" or record.get("status") != "pending":
        return False, "NOT_PENDING"
    created_at = _timestamp(record.get("created_at"))
    # Older ACE records use local wall-clock timestamps without an offset.
    # The supplied historical cutoff is the authority for interpreting them;
    # never compare aware and naive values or silently treat a legacy record
    # as newer solely because its offset was omitted.
    if created_at is not None and created_at.tzinfo is None and cutoff.tzinfo is not None:
        created_at = created_at.replace(tzinfo=cutoff.tzinfo)
    if created_at is None or created_at >= cutoff:
        return False, "OUTSIDE_CUTOFF"
    if record.get("lease_owner") or record.get("claim_id"):
        return False, "OPEN_LEASE"
    if record.get("depends_on") or record.get("parent_task"):
        return False, "DEPENDENCY_PRESENT"
    admission = _admission(record)
    if admission.get("source_type") != "system_observation" or not admission.get("evidence"):
        return False, "ADMISSION_OR_EVIDENCE_INCOMPLETE"
    if _signature(record) is None:
        return False, "SEMANTIC_SIGNATURE_UNAVAILABLE"
    return True, "ELIGIBLE"


def build_dry_run(root: Path = BASE_DIR, *, cutoff_at: str) -> Dict[str, Any]:
    """Return a stable dry-run proposal without changing any task record."""
    cutoff = _timestamp(cutoff_at)
    if cutoff is None:
        raise ValueError("cutoff_at must be an ISO-8601 timestamp")
    pool = Path(root) / "task_pool"
    before = _snapshot(pool)
    excluded = []
    grouped: Dict[tuple[str, str], list[Dict[str, Any]]] = {}
    for item in before:
        record = item["record"]
        rule = str(_outputs(record).get("conversion_rule", ""))
        if rule not in TARGET_RULES:
            continue
        allowed, reason = _eligible(item, cutoff)
        if not allowed:
            excluded.append({"task_id": record.get("task_id"), "reason": reason})
            continue
        grouped.setdefault(_signature(record), []).append(item)

    groups = []
    for (rule, signature), members in sorted(grouped.items()):
        members.sort(key=lambda item: (
            -int(item["record"].get("review_count", 0) or 0),
            str(item["record"].get("created_at", "")),
            str(item["record"].get("task_id", "")),
        ))
        if len(members) < 2:
            excluded.append({"task_id": members[0]["record"].get("task_id"), "reason": "SINGLETON_SEMANTIC_GROUP"})
            continue
        canonical, donors = members[0], members[1:]
        if rule == "recent_errors":
            groups.append({
                "rule": rule,
                "semantic_signature": signature,
                "decision": "needs_review",
                "reason_codes": ["RECENT_ERROR_CONTINUITY_NOT_PROVEN"],
                "canonical_task_id": canonical["record"].get("task_id"),
                "donor_task_ids": [item["record"].get("task_id") for item in donors],
            })
            continue
        groups.append({
            "rule": rule,
            "semantic_signature": signature,
            "decision": "merge_candidate",
            "reason_codes": ["PENDING_SEMANTIC_EQUIVALENCE"],
            "canonical_task_id": canonical["record"].get("task_id"),
            "donor_task_ids": [item["record"].get("task_id") for item in donors],
            "projected_transition": "pending_to_blocked_via_existing_state_machine",
        })

    after = _snapshot(pool)
    merge_candidates = sum(group["decision"] == "merge_candidate" for group in groups)
    return {
        "schema_version": 1,
        "mode": "dry_run",
        "pool": str(pool),
        "cutoff_at": cutoff.isoformat(),
        "snapshot": {
            "before_digest": _digest(before),
            "after_digest": _digest(after),
            "stable": _digest(before) == _digest(after),
            "record_count": len(before),
        },
        "groups": groups,
        "excluded": excluded,
        "summary": {
            "merge_candidate_groups": merge_candidates,
            "needs_review_groups": sum(group["decision"] == "needs_review" for group in groups),
            "donor_count": sum(len(group["donor_task_ids"]) for group in groups if group["decision"] == "merge_candidate"),
            "excluded_count": len(excluded),
            "apply_authorized": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only ACE TaskPool duplicate reconciliation dry run")
    parser.add_argument("--root", type=Path, default=BASE_DIR)
    parser.add_argument("--cutoff-at", required=True)
    args = parser.parse_args()
    print(json.dumps(build_dry_run(args.root, cutoff_at=args.cutoff_at), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

