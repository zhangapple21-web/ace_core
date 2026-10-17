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

    # A rule with no incident on file is not broken; the net is simply idle. Two
    # distinct findings share this watch, because both are ways a pointer stops
    # meaning what it says, and both were present in this repository:
    #
    #   STUCK_NO_OBSERVATION  the machinery cannot clear the pointer at all - a
    #                         safety net that has no input
    #   CONDITION_STILL_TRUE  the pointer is accurate: the condition it names is
    #                         still true, and a terminal task was archived over it.
    #                         This is unfixed work wearing a closed task's name, and
    #                         filtering it out here would have made this watch go
    #                         quiet about the very thing it was built to surface.
    findings: List[Dict[str, Any]] = []
    for row in report["incidents"]:
        verdict = row["verdict"]
        if verdict not in ("STUCK_NO_OBSERVATION", "CONDITION_STILL_TRUE"):
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
        if verdict == "STUCK_NO_OBSERVATION":
            detail = ("the rule's category has produced no unprocessed observation, so "
                      "the reconciler cannot see it and the pointer cannot be cleared")
        else:
            condition = row.get("live_condition") or {}
            detail = (f"the condition is still true: {condition.get('state_key')}="
                      f"{condition.get('value')!r} against {condition.get('threshold')!r}"
                      f"; task {row['task_id']} is terminal, so the work was closed "
                      f"without the condition changing")
        findings.append({
            "rule": row["incident"],
            "verdict": verdict,
            "category": row["category"],
            "task_id": row["task_id"],
            "task_terminal": row["task_terminal"],
            "task_status": row.get("task_found_in"),
            "last_observed_at": observed,
            "unverified_days": age_days,
            "live_condition": row.get("live_condition"),
            "detail": detail,
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
            # The age gate belongs to STUCK_NO_OBSERVATION alone. There the age is
            # the evidence: a pointer nobody can clear is only a standing claim
            # once it has stood for a while, and surfacing it on day one would
            # train the blindness this watch exists to remove.
            #
            # CONDITION_STILL_TRUE is not a claim about age. `_live_condition()`
            # measures it against the real state on every run, so a fresh
            # last_observed_at is the opposite of a reason to stay quiet. Applying
            # one gate to both made this watch go silent the moment the lifecycle
            # fix began refreshing last_observed_at every cycle: the condition
            # became better evidenced and therefore unreportable, which is the
            # failure mode the age gate was written to prevent and not to cause.
            if (finding["verdict"] == "STUCK_NO_OBSERVATION"
                    and age is not None and age < STALE_POINTER_DAYS):
                continue
            # An age that cannot be computed is itself unverified and still
            # surfaces: the guard above needs a real, small age to stay quiet.
            shown_age = f"{age} days" if age is not None else "an unknown number of days"
            condition = finding.get("live_condition") or {}
            if finding["verdict"] == "CONDITION_STILL_TRUE":
                description = (
                    f"incident {finding['rule']} is open work closed on paper: "
                    f"{condition.get('state_key')}={condition.get('value')!r} still "
                    f"breaches {condition.get('threshold')!r} and task "
                    f"{finding['task_id']} is terminal"
                )
                severity = "high"
            else:
                description = (f"incident rule {finding['rule']} cannot be reconciled: "
                               f"no {finding['category']!r} observation reaches the "
                               f"converter; pointer to {finding['task_id']} unverified "
                               f"for {shown_age}")
                severity = "medium"
            observer.record(
                description=description,
                system_state={
                    "rule": finding["rule"],
                    "verdict": finding["verdict"],
                    "category": finding["category"],
                    "task_id": finding["task_id"],
                    "task_terminal": finding["task_terminal"],
                    "unverified_days": finding["unverified_days"],
                    "live_condition": condition,
                    "contract_version": CONTRACT_VERSION,
                },
                severity=severity,
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