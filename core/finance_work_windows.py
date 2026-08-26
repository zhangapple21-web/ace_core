"""Auditable Finance workload windows over the existing daemon lifecycle.

This module does not schedule, create tasks, call models, or publish advice.
At open validation it may invoke one bounded data-refresh callback owned by
the existing daemon, then records whether the refreshed evidence supports a
research-only or production financial path.
"""

import json
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from core.stock_data_reliability import MarketState, assess_market_state


WINDOWS = {
    "morning_observation": (time(9, 0), time(9, 29, 59)),
    "open_validation": (time(9, 30), time(10, 0)),
    "midday_review": (time(12, 30), time(13, 0)),
    "close_review": (time(15, 15), time(16, 0)),
    "next_day_watchlist": (time(16, 0), time(23, 59, 59)),
}


class FinanceWorkWindows:
    def __init__(
        self,
        data_dir: str,
        timezone_name: str = "Asia/Shanghai",
        observer=None,
        data_refresh=None,
        public_sentiment=None,
    ):
        self.data_dir = Path(data_dir)
        self.timezone = ZoneInfo(timezone_name)
        self.observer = observer
        self.data_refresh = data_refresh
        self.public_sentiment = public_sentiment
        self.matrix_path = self.data_dir / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
        self.benchmark_path = self.data_dir / "stock_data_evidence" / "stock_data_benchmark_latest.json"
        self.report_path = self.data_dir / "finance_work_windows_latest.json"

    def _evidence_refs(self):
        return [
            str(path) for path in (self.matrix_path, self.benchmark_path)
            if path.exists()
        ]

    def _retained_refresh_result(self) -> Optional[Dict[str, Any]]:
        """Recover a prior window's bounded refresh summary from its evidence.

        Early reports retained only ``already_attempted_for_window``.  The
        benchmark remains the source of truth, so this is an evidence summary,
        not a new request and not a claim that data passed admission.
        """
        try:
            benchmark = json.loads(self.benchmark_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        refresh = benchmark.get("incremental_refresh", {})
        if not isinstance(refresh, dict) or refresh.get("kind") != "trading_window_live_operations":
            return None
        return {
            "status": "completed",
            "completed_at": benchmark.get("completed_at") or benchmark.get("summary", {}).get("generated_at"),
            "sources": list(refresh.get("sources", [])),
            "operations": list(refresh.get("operations", [])),
            "refreshed_probe_count": refresh.get("refreshed_probe_count", 0),
            "evidence_recovered": True,
        }

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
        phase_two_status = matrix.get("phase_two_admission", {}).get("status")
        if phase_two_status == "ADMITTED" and admitted == required:
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
        previous = {}
        try:
            previous = json.loads(self.report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        daily_windows = (
            dict(previous.get("daily_windows", {}))
            if previous.get("date") == observed_at.date().isoformat()
            else {}
        )
        refresh_result = None
        sentiment_result = None
        if (
            due == "open_validation"
            and assess_market_state(observed_at).state == MarketState.TRADING
            and self.data_refresh is not None
        ):
            prior_window = daily_windows.get(due, {})
            if isinstance(prior_window, dict) and prior_window.get("data_refresh_attempted"):
                # Later daemon cycles must not hide the real bounded refresh
                # behind a bare dedup marker.  Preserve its auditable result
                # so the Daily Shift can answer what was actually observed
                # without issuing a second market-data request.
                refresh_result = {
                    "status": "already_attempted_for_window",
                    "initial_result": (
                        self._retained_refresh_result()
                        if not isinstance(prior_window.get("data_refresh"), dict)
                        or prior_window["data_refresh"].get("status") == "already_attempted_for_window"
                        else prior_window["data_refresh"]
                    ),
                }
            else:
                try:
                    value = self.data_refresh()
                    refresh_result = value if isinstance(value, dict) else {"status": "completed"}
                except Exception as exc:
                    refresh_result = {
                        "status": "failed",
                        "reason": type(exc).__name__,
                    }

        if due and self.public_sentiment is not None:
            prior_window = daily_windows.get(due, {})
            prior_sentiment = prior_window.get("public_sentiment") if isinstance(prior_window, dict) else None
            if isinstance(prior_sentiment, dict):
                sentiment_result = {"status": "already_observed_for_window", "initial_result": prior_sentiment}
            else:
                try:
                    sentiment_result = self.public_sentiment.collect(window=due, observed_at=observed_at)
                except Exception as exc:
                    sentiment_result = {"status": "unavailable", "reason": type(exc).__name__}

        status = self._finance_status()
        if due is None:
            window_status = "WINDOW_NOT_DUE"
        elif status in {"DEGRADED", "RESEARCH_ONLY"}:
            window_status = "RESEARCH_ONLY"
        else:
            window_status = "NO_VALID_OBSERVATION"
        window_record = {
            "observed_at": observed_at.isoformat(),
            "window_status": window_status,
            "finance_status": status,
            "evidence_refs": self._evidence_refs(),
            "data_refresh_attempted": refresh_result is not None,
            "data_refresh": refresh_result,
            "public_sentiment": sentiment_result,
        }
        if due:
            daily_windows[due] = window_record
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
            "evidence_refs": self._evidence_refs(),
            "data_refresh": refresh_result,
            "public_sentiment": sentiment_result,
            "daily_windows": daily_windows,
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
            report["observation_recorded"] = True
        else:
            report["observation_recorded"] = False
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
