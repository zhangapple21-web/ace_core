"""Hourly evidence ledger for the existing TaskPool lifecycle service."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


class HourlyTaskService:
    def __init__(self, data_dir: str):
        self.path = Path(data_dir) / "hourly_task_service_latest.json"

    @staticmethod
    def _execution_evidence(executor_context: Mapping[str, Any] | None) -> dict[str, Any]:
        """Classify attribution without turning a report into runtime proof."""
        context = dict(executor_context or {})
        pid = context.get("pid")
        run_id = context.get("run_id")
        if (
            isinstance(pid, int)
            and pid > 0
            and isinstance(run_id, str)
            and run_id
            and context.get("lock_binding") == "matched"
        ):
            executor = {"pid": pid, "run_id": run_id, "lock_binding": "matched"}
            return {
                "status": "DAEMON_CONTEXT_BOUND",
                "runtime_proof": False,
                "executor": executor,
                "semantics": "daemon context is an attributable execution receipt, not independent runtime proof",
            }
        return {
            "status": "UNATTRIBUTED_LOCAL_CALL",
            "runtime_proof": False,
            "executor": None,
            "semantics": "report generation alone does not prove that the sole daemon executed this lifecycle",
        }

    def record(
        self,
        pending_before: int,
        lifecycle_result: dict,
        *,
        executor_context: Mapping[str, Any] | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        hour = now.strftime("%Y-%m-%dT%H:00Z")
        researched = int(lifecycle_result.get("researched", 0))
        execution_evidence = self._execution_evidence(executor_context)
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
            "existing_daemon_lifecycle": execution_evidence["status"] == "DAEMON_CONTEXT_BOUND",
            "execution_evidence": execution_evidence,
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
