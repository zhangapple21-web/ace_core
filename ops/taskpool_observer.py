import argparse
import json
from datetime import datetime
from pathlib import Path


def _parse_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    return timestamp.replace(tzinfo=None)


def _in_window(value, start, end):
    return start <= _parse_timestamp(value) <= end


def _load_tasks(pool_dir):
    for path in Path(pool_dir).rglob("RQ-*.json"):
        try:
            with path.open(encoding="utf-8") as handle:
                yield json.load(handle)
        except (OSError, ValueError, json.JSONDecodeError):
            continue


def _claim_events(task):
    return [
        event for event in task.get("audit_log", [])
        if event.get("event") == "transition"
        and event.get("actor") == "researcher"
        and event.get("reason") == "lease_claimed"
        and event.get("to") == "active"
        and event.get("at")
    ]


def _transitions(task, start, end):
    transitions = []
    for event in task.get("audit_log", []):
        if event.get("event") != "transition" or not event.get("at"):
            continue
        try:
            if _in_window(event["at"], start, end):
                transitions.append(event)
        except ValueError:
            continue
    return sorted(transitions, key=lambda event: _parse_timestamp(event["at"]))


def _first_after(events, timestamp, predicate):
    for event in events:
        if _parse_timestamp(event["at"]) > _parse_timestamp(timestamp) and predicate(event):
            return event
    return None


def replay_window(pool_dir, start_at, end_at):
    start = _parse_timestamp(start_at)
    end = _parse_timestamp(end_at)
    claims = []
    inconsistencies = []

    for task in _load_tasks(pool_dir):
        persisted_claims = _claim_events(task)
        task_claims = [
            event for event in persisted_claims
            if _in_window(event["at"], start, end)
        ]
        events = _transitions(task, start, end)
        for claim in task_claims:
            research = _first_after(
                events,
                claim["at"],
                lambda event: event.get("actor") == "researcher"
                and event.get("from") == "active"
                and event.get("to") == "review",
            )
            validation = None
            if research:
                validation = _first_after(
                    events,
                    research["at"],
                    lambda event: event.get("actor") == "validator"
                    and event.get("from") == "review",
                )
            record = {
                "task_id": task["task_id"],
                "priority": task.get("priority"),
                "at": claim["at"],
                "research": research,
                "validation": validation,
                "claim_count": len(persisted_claims),
                "fencing_token": task.get("fencing_token", 0),
                "last_claimed_at": task.get("last_claimed_at", ""),
                "latest_claim_at": max(
                    persisted_claims,
                    key=lambda event: _parse_timestamp(event["at"]),
                )["at"],
                "status": task.get("status"),
            }
            claims.append(record)
            if research is None:
                inconsistencies.append({
                    "task_id": task["task_id"],
                    "claim_at": claim["at"],
                    "reason": "claim_without_research_transition",
                })
            elif validation is None:
                inconsistencies.append({
                    "task_id": task["task_id"],
                    "claim_at": claim["at"],
                    "reason": "research_without_validation_transition",
                })

        if task_claims:
            if task.get("fencing_token", 0) < len(persisted_claims):
                inconsistencies.append({
                    "task_id": task["task_id"],
                    "reason": "fencing_token_below_claim_count",
                })
            latest = max(persisted_claims, key=lambda event: _parse_timestamp(event["at"]))
            last_claimed_at = task.get("last_claimed_at", "")
            if last_claimed_at:
                if _parse_timestamp(last_claimed_at) > _parse_timestamp(latest["at"]):
                    inconsistencies.append({
                        "task_id": task["task_id"],
                        "claim_at": latest["at"],
                        "reason": "last_claimed_at_after_latest_audit_claim",
                    })
            else:
                inconsistencies.append({
                    "task_id": task["task_id"],
                    "claim_at": latest["at"],
                    "reason": "missing_last_claimed_at",
                })

    claims.sort(key=lambda record: _parse_timestamp(record["at"]))
    return {
        "window": {"start": start_at, "end": end_at},
        "counts": {
            "claims": len(claims),
            "research": sum(record["research"] is not None for record in claims),
            "validation": sum(record["validation"] is not None for record in claims),
        },
        "claims": claims,
        "inconsistencies": inconsistencies,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pool_dir")
    parser.add_argument("start_at")
    parser.add_argument("end_at")
    arguments = parser.parse_args()
    print(json.dumps(replay_window(arguments.pool_dir, arguments.start_at, arguments.end_at), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
