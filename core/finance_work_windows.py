"""Auditable Finance workload windows over the existing daemon lifecycle.

This module does not schedule, create tasks, call models, or publish advice.
It records which observation window is due and whether the existing evidence
supports research-only work or a production financial path.
"""

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


WINDOWS = {
    "overnight_observation": (time(0, 0), time(9, 0)),
    "open_validation": (time(9, 30), time(10, 0)),
    "midday_review": (time(12, 30), time(13, 0)),
    "close_review": (time(15, 15), time(16, 0)),
    "next_day_watchlist": (time(16, 0), time(23, 59, 59)),
}


class FinanceWorkWindows:
    def __init__(self, data_dir: str, timezone_name: str = "Asia/Shanghai", observer=None):
        self.data_dir = Path(data_dir)
        self.timezone = ZoneInfo(timezone_name)
        self.observer = observer
        self.matrix_path = self.data_dir / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
        self.report_path = self.data_dir / "finance_work_windows_latest.json"

    def _finance_status(self) -> str:
        try:
            matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "WATCH_ONLY"
        operations = matrix.get("phase_two_admission", {}).get("core_operations", {})
        required = {"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"}
        admitted = {
            key for key in required
            if isinstance(operations.get(key), dict)
            and operations[key].get("production_sources")
            and operations[key].get("has_independent_cross_validation") is True
        }
        if admitted == required:
            return "FULL_READY"
        if admitted:
            return "DEGRADED"
        return "RESEARCH_ONLY"

    def _window(self, local_now: datetime) -> Optional[str]:
        current = local_now.time()
        for name, (start, end) in WINDOWS.items():
            if start <= current <= end:
                return name
        return None

    def build(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        observed_at = now.astimezone(self.timezone) if now else datetime.now(self.timezone)
        due = self._window(observed_at)
        status = self._finance_status()
        if due is None:
            window_status = "WINDOW_NOT_DUE"
        elif status in {"DEGRADED", "RESEARCH_ONLY"}:
            window_status = "RESEARCH_ONLY"
        else:
            window_status = "NO_VALID_OBSERVATION"
        report = {
            "schema_version": 1,
            "observed_at": observed_at.isoformat(),
            "date": observed_at.date().isoformat(),
            "timezone": str(self.timezone),
            "window": due,
            "window_status": window_status,
            "finance_status": status,
            "task_created": False,
            "model_call": False,
            "recommendation_allowed": False,
            "evidence_refs": [str(self.matrix_path)] if self.matrix_path.exists() else [],
            "research_question": (
                "在当前数据准入状态下，哪些金融观察仍可进行，哪些字段缺口阻断实时验证？"
                if due else None
            ),
            "next_action": "record_observation_and_wait_for_independent_evidence" if due else "wait_for_next_window",
            "cognitive_workstreams": [
                "market_state_research",
                "data_lineage_audit",
                "prediction_review",
                "next_day_hypothesis",
            ] if due else [],
        }
        if due and self.observer is not None:
            observation = self.observer.record(
                description=f"Finance window {due} observation for {observed_at.date().isoformat()}",
                system_state={
                    "finance_window": due,
                    "window_status": window_status,
                    "finance_status": status,
                    "research_question": report["research_question"],
                    "expected_result": "A bounded market-state and data-quality finding; no recommendation.",
                    "verification_method": "Compare existing source evidence at the next observation window.",
                    "evidence_refs": report["evidence_refs"],
                    "date": observed_at.date().isoformat(),
                },
                severity="medium",
                source="finance_work_window",
                category="financial_research",
                auto_generated=True,
            )
            report["observation_id"] = observation.obs_id
            report["observation_created"] = True
        else:
            report["observation_created"] = False
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
