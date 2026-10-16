"""An incident tracker that cannot see anything must say so out loud.

A `persistent_semantic_incident` is meant to be forgotten once an observation of
its category proves recovery. That reconciliation runs inside the observation
converter's loop over the unprocessed queue. If a rule's category never appears
there, the incident can never be forgotten - and the incident file goes on
reporting it as open while the remediation task sits archived. Two were found that
way: fragment_backlog, 18 days old, and cross_agent_idle, 7 days, both pointing at
tasks archived minutes after creation.

This is the same shape as an unwired component: a rule that exists, has tests, and
can never fire. The dead-component watch already escalates that condition into the
`structural_gap` observation channel; this does the same for incident rules, so a
broken safety net becomes visible work instead of a silent, permanent claim.

It records nothing about market or lexicon conditions. It reports one fact: this
rule cannot currently be reconciled, so nobody should read its incident file entry
as live.

Read the detection in ops/diagnose_semantic_incidents.py; this only raises it.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ops.diagnose_semantic_incidents import (  # noqa: E402
    INCIDENTS,
    diagnose,
)

CONTRACT_VERSION = "ace.incident_reachability_watch.v1"
SNAPSHOT = "08_GOVERNANCE/structural_integrity/incident_reachability_snapshot.json"

# A pointer older than this has not been re-verified in a long time. Its presence
# is not evidence that anything is watching it any more.
STALE_POINTER_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def run(root: Path = ROOT, observer: Any = None, *, force: bool = False) -> Dict[str, Any]:
    """Report every persistent incident rule that cannot currently be reconciled."""
    report = diagnose()
    # diagnose() returns a bare marker when there is no incident file at all, which
    # is not a broken machine. Indexing its queue fields directly raised KeyError;
    # take them with a default so "no incidents" reports nothing and stops.
    if report.get("status") == "NO_INCIDENT_FILE":
        return {
            "status": "NO_INCIDENT_FILE",
            "contract_version": CONTRACT_VERSION,
            "unreachable_rules": 0,
            "escalated": 0,
            "snapshot": "",
        }

    # A rule with no incident on file is not broken; the net is simply idle. Only a
    # pointer that exists and cannot be cleared is a gap.
    findings: List[Dict[str, Any]] = []
    for row in report["incidents"]:
        if row["verdict"] != "STUCK_NO_OBSERVATION":
            continue
        observed = str(row.get("last_observed_at") or "")
        age_days = None
        if observed:
            try:
                # last_observed_at is written naive (no offset) while _now() is
                # timezone-aware. Subtracting the two raised TypeError, which the
                # guard below read as "not old enough" and skipped - the exact
                # silent blindness this watch exists to remove. Parse naive values
                # as UTC so the age is real.
                parsed = datetime.fromisoformat(observed)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age_days = (_now() - parsed).days
            except (ValueError, TypeError):
                age_days = None
        findings.append({
            "rule": row["incident"],
            "category": row["category"],
            "task_id": row["task_id"],
            "task_terminal": row["task_terminal"],
            "last_observed_at": observed,
            "unverified_days": age_days,
            "detail": ("the rule's category has produced no unprocessed observation, so "
                       "the reconciler cannot see it and the pointer cannot be cleared"),
        })

    snapshot = {
        "contract_version": CONTRACT_VERSION,
        "at": _iso(_now()),
        "unprocessed_queue_size": report["unprocessed_queue_size"],
        "convert_limit": report["convert_limit"],
        "queue_categories": report["queue_categories"],
        "unreachable_incident_rules": [f["rule"] for f in findings],
        "findings": findings,
    }

    escalated: List[Dict[str, Any]] = []
    if observer is not None:
        for finding in findings:
            age = finding["unverified_days"]
            # A pointer whose age cannot be computed is itself unverified, and must
            # surface. Skipping it silently would repeat the failure this watch
            # exists to catch.
            if age is not None and age < STALE_POINTER_DAYS:
                # Not yet old enough to be a standing claim. Surfacing it on day one
                # would train the same blindness this watch exists to remove.
                continue
            shown_age = f"{age} days" if age is not None else "an unknown number of days"
            observer.record(
                description=(f"incident rule {finding['rule']} cannot be reconciled: "
                             f"no {finding['category']!r} observation reaches the converter; "
                             f"pointer to {finding['task_id']} unverified for {shown_age}"),
                system_state={
                    "rule": finding["rule"],
                    "category": finding["category"],
                    "task_id": finding["task_id"],
                    "task_terminal": finding["task_terminal"],
                    "unverified_days": finding["unverified_days"],
                    "contract_version": CONTRACT_VERSION,
                },
                severity="medium",
                source="incident_reachability_watch",
                category="structural_gap",
                dedup_key=f"incident_unreachable:{finding['rule']}",
            )
            escalated.append(finding)

    snapshot_path = root / SNAPSHOT
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from core.window_write import write_window_artifact

        write_window_artifact(root, SNAPSHOT, payload, lane="governance-lane",
                             actor="incident_reachability_watch")
    except Exception:
        snapshot_path.write_text(payload, encoding="utf-8")

    return {
        "status": "SCANNED",
        "contract_version": CONTRACT_VERSION,
        "unreachable_rules": len(findings),
        "escalated": len(escalated),
        "snapshot": str(snapshot_path.relative_to(root)).replace("\\", "/"),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    observer = None
    try:
        from core.observation import RuntimeObserver

        observer = RuntimeObserver(
            data_dir=str(Path(args.root) / "06_RUNTIME" / "ace" / "data" / "observations"))
    except Exception:
        observer = None

    result = run(Path(args.root), observer)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())