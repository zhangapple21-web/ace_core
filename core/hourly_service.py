"""Hourly evidence ledger for the existing TaskPool lifecycle service."""

import json
from datetime import datetime, timezone
from pathlib import Path


class HourlyTaskService:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "hourly_task_service_latest.json"

    def record(self, pending_before: int, lifecycle_result: dict) -> dict:
        now = datetime.now(timezone.utc)
        hour = now.strftime("%Y-%m-%dT%H:00Z")
        researched = int(lifecycle_result.get("researched", 0))
        report = {
            "schema_version": 1,
            "hour": hour,
            "checked_at": now.isoformat(),
            "pending_observed": pending_before,
            "claim_and_research": researched,
            "validated": int(lifecycle_result.get("validated", 0)),
            "archived": int(lifecycle_result.get("archived", 0)),
            "service_status": (
                "WORK_SERVICED" if researched
                else "NO_PENDING_WORK" if pending_before == 0
                else "ELIGIBLE_WORK_NOT_SERVICED"
            ),
            "scheduler_created": False,
            "existing_daemon_lifecycle": True,
        }
        history = {}
        try:
            prior = json.loads(self.path.read_text(encoding="utf-8"))
            history = dict(prior.get("history", {}))
        except (OSError, json.JSONDecodeError):
            pass
        history[hour] = report.copy()
        report["history"] = dict(sorted(history.items())[-48:])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
