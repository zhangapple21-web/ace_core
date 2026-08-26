"""Product-facing daily shift ledger built from existing production evidence."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class DailyShift:
    def __init__(self, task_pool, data_dir: str):
        self.task_pool = task_pool
        self.data_dir = Path(data_dir)
        self.json_path = self.data_dir / "daily_shift_latest.json"
        self.md_path = self.data_dir / "daily_shift_latest.md"

    @staticmethod
    def _read(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def build(self, date: Optional[str] = None, *, daemon_state_path: Optional[str] = None) -> Dict[str, Any]:
        day = date or datetime.now(timezone.utc).date().isoformat()
        state = self._read(Path(daemon_state_path)) if daemon_state_path else {}
        growth = self._read(self.data_dir / "daily_growth_latest.json")
        window = self._read(self.data_dir / "finance_work_windows_latest.json")
        sentiment = self._read(self.data_dir / "public_sentiment_latest.json")
        refresh = window.get("data_refresh") if isinstance(window.get("data_refresh"), dict) else {}
        if refresh.get("status") == "already_attempted_for_window":
            initial = refresh.get("initial_result")
            refresh_evidence = initial if isinstance(initial, dict) else refresh
        else:
            refresh_evidence = refresh
        counts = {}
        transitions = {key: 0 for key in ("claim", "research", "validation", "approved", "archived")}
        for task in self.task_pool.list_tasks(limit=10000):
            counts[task.status] = counts.get(task.status, 0) + 1
            for event in task.audit_log or []:
                if not isinstance(event, dict):
                    continue
                if event.get("event") != "transition":
                    continue
                if not str(event.get("at", "")).startswith(day):
                    continue
                pair = (event.get("from"), event.get("to"), event.get("reason"))
                if pair == ("pending", "active", "lease_claimed"):
                    transitions["claim"] += 1
                elif event.get("to") == "review":
                    transitions["research"] += 1
                if event.get("from") == "review" and event.get("actor") == "validator":
                    transitions["validation"] += 1
                if event.get("to") == "approved":
                    transitions["approved"] += 1
                if event.get("to") == "archived":
                    transitions["archived"] += 1
        report = {
            "schema_version": 1,
            "date": day,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "daemon": {
                "pid": state.get("pid"),
                "run_id": state.get("run_id"),
                "cycle_status": state.get("cycle_progress", {}).get("cycle_status"),
                "stop_reason": state.get("cycle_progress", {}).get("stop_reason"),
            },
            "windows": window,
            "finance_live_refresh": {
                key: refresh_evidence.get(key)
                for key in ("status", "completed_at", "sources", "operations", "refreshed_probe_count")
                if key in refresh_evidence
            },
            "hourly_service": self._read(self.data_dir / "hourly_task_service_latest.json"),
            "completed_work": {
                "outcome": growth.get("outcome"),
                "archived_task_count": growth.get("archived_task_count", 0),
                "attempted_production_model_call_count": growth.get("attempted_production_model_call_count", 0),
                "successful_production_model_call_count": growth.get("successful_production_model_call_count", growth.get("production_model_call_count", 0)),
                "production_model_call_count": growth.get("production_model_call_count", 0),
                "production_model_call_semantics": growth.get("production_model_call_semantics", {}),
                "experience_deposition": growth.get("archived_task_count", 0) > 0,
            },
            "model_performance": growth.get("model_performance_ledger", {}),
            "taskpool": {"status_counts": counts, "lifecycle_transitions": transitions},
            "finance_status": growth.get("finance_status", window.get("finance_status", "UNKNOWN")),
            "public_sentiment": {
                key: sentiment.get(key)
                for key in ("status", "window", "independent_content_source_count", "admission_ready", "reason")
                if key in sentiment
            },
            "advisor_status": "BLOCKED",
            "risk_status": "NOT_READY",
            "owner_tg": "OFF",
            "next_observation": window.get("next_action"),
            "no_synthetic_work": True,
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.md_path.write_text(
            "\n".join([
                f"# ACE DAILY SHIFT — {day}", "",
                f"- Daemon: PID `{report['daemon']['pid']}`, run `{report['daemon']['run_id']}`",
                f"- Cycle: `{report['daemon']['cycle_status']}` / `{report['daemon']['stop_reason']}`",
                f"- Finance: `{report['finance_status']}`; window `{window.get('window_status', 'UNKNOWN')}`",
                f"- Public sentiment: `{report['public_sentiment'].get('status', 'NOT_OBSERVED')}`; independent content sources `{report['public_sentiment'].get('independent_content_source_count', 0)}`; admission-ready `{report['public_sentiment'].get('admission_ready', False)}`",
                f"- Live data refresh: `{report['finance_live_refresh'].get('status', 'NOT_RUN')}`; operations `{report['finance_live_refresh'].get('operations', [])}`; sources `{report['finance_live_refresh'].get('sources', [])}`",
                f"- Completed: `{report['completed_work']['archived_task_count']}` archived tasks, `{report['completed_work']['attempted_production_model_call_count']}` attempted / `{report['completed_work']['successful_production_model_call_count']}` successful production model calls",
                f"- Model performance: `{report['model_performance'].get('group_count', 0)}` groups, shadow-only `{report['model_performance'].get('shadow_only', True)}`",
                f"- TaskPool transitions: `{transitions}`",
                "- Advisor: `BLOCKED`; Risk: `NOT_READY`; Owner TG: `OFF`",
                f"- Next observation: `{report['next_observation']}`",
                "- Synthetic work: `NO`",
                "",
            ]),
            encoding="utf-8",
        )
        return report
