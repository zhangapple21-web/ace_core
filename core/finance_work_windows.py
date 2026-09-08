"""Auditable Finance workload windows over the existing daemon lifecycle.

This module does not schedule, create tasks, call models, or publish advice.
At open validation it may invoke one bounded data-refresh callback owned by
the existing daemon, then records whether the refreshed evidence supports a
research-only or production financial path.
"""

import json
import hashlib
import os
from datetime import datetime, time
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from core.stock_data_reliability import MarketState, assess_market_state
from core.data_admission_recovery import DataAdmissionRecovery


WINDOWS = {
    "morning_observation": (time(9, 0), time(9, 29, 59)),
    "open_validation": (time(9, 30), time(10, 0)),
    "midday_review": (time(12, 30), time(13, 0)),
    "close_review": (time(15, 15), time(16, 0)),
    "next_day_watchlist": (time(16, 0), time(23, 59, 59)),
}

# One task, with a moving discovery window.  These are phases of the existing
# finance lifecycle; they are not an additional scheduler or a fixed 09:25
# to 09:35 job.
DISCOVERY_TASK_VERSION = "ace.early_opportunity_discovery.v1"
DISCOVERY_PHASES = (
    "market_universe_candidate_pool",
    "dynamic_discovery_window",
    "incremental_refresh",
    "actionability_gate",
    "ace_decision",
    "xiaoyan_expression",
)


class FinanceWorkWindows:
    def __init__(
        self,
        data_dir: str,
        timezone_name: str = "Asia/Shanghai",
        observer=None,
        data_refresh=None,
        public_sentiment=None,
        candidate_snapshot_provider=None,
        refresh_each_cycle: bool = False,
    ):
        self.data_dir = Path(data_dir)
        self.timezone = ZoneInfo(timezone_name)
        self.observer = observer
        self.data_refresh = data_refresh
        self.public_sentiment = public_sentiment
        # The provider is an observation adapter only.  It may return a
        # point-in-time candidate snapshot, but it cannot admit or publish a
        # recommendation.  Keeping it injectable lets the existing daemon
        # own the market-data implementation and keeps this window a ledger.
        self.candidate_snapshot_provider = candidate_snapshot_provider
        self.refresh_each_cycle = bool(refresh_each_cycle)
        self.matrix_path = self.data_dir / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
        self.benchmark_path = self.data_dir / "stock_data_evidence" / "stock_data_benchmark_latest.json"
        self.report_path = self.data_dir / "finance_work_windows_latest.json"
        self.discovery_ledger_path = self.data_dir / "stock_data_evidence" / "early_opportunity_discovery.v1.jsonl"
        self.recovery = DataAdmissionRecovery(self.data_dir)

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

    @staticmethod
    def _initial_window_result(value: Any, marker: str) -> Any:
        """Return the first observed result behind a same-window dedup marker.

        ``build()`` runs on every daemon cycle.  Keeping a marker inside the
        previous marker causes the persisted ledger to grow on every cycle,
        even though no new observation occurred.  Preserve the original
        evidence instead, with a small bound for malformed historic payloads.
        """
        result = value
        for _ in range(8):
            if not isinstance(result, dict) or result.get("status") != marker:
                break
            initial = result.get("initial_result")
            if not isinstance(initial, dict):
                break
            result = initial
        return result

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
            previous = {}
        if not isinstance(previous, dict):
            previous = {}
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
            if (
                not self.refresh_each_cycle
                and isinstance(prior_window, dict)
                and prior_window.get("data_refresh_attempted")
            ):
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
                sentiment_result = {
                    "status": "already_observed_for_window",
                    "initial_result": self._initial_window_result(
                        prior_sentiment, "already_observed_for_window"
                    ),
                }
            else:
                try:
                    sentiment_result = self.public_sentiment.collect(window=due, observed_at=observed_at)
                except Exception as exc:
                    sentiment_result = {"status": "unavailable", "reason": type(exc).__name__}

        status = self._finance_status()
        try:
            matrix = json.loads(self.matrix_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            matrix = {}
        recovery = self.recovery.build(matrix, observed_at=observed_at.isoformat())
        if due is None:
            window_status = "WINDOW_NOT_DUE"
        elif status in {"DEGRADED", "RESEARCH_ONLY"}:
            window_status = "RESEARCH_ONLY"
        else:
            window_status = "NO_VALID_OBSERVATION"
        market_state = (
            "RESEARCH_ONLY_DATA_DEGRADED"
            if status in {"DEGRADED", "RESEARCH_ONLY"}
            else "NO_VALID_OBSERVATION"
        )

        discovery_snapshot = None
        if due and self.candidate_snapshot_provider is not None:
            try:
                value = self.candidate_snapshot_provider(
                    window=due,
                    observed_at=observed_at,
                )
                discovery_snapshot = value if isinstance(value, dict) else {
                    "status": "DATA_UNAVAILABLE",
                    "reason": "candidate_snapshot_provider_returned_non_mapping",
                }
            except Exception as exc:
                discovery_snapshot = {
                    "status": "DATA_UNAVAILABLE",
                    "reason": f"candidate_snapshot_provider_failed:{type(exc).__name__}",
                }
        # Keep the whole early-discovery flow visible in the same auditable
        # report.  The phase names describe ownership and ordering; actual
        # candidate admission remains subject to existing data gates.
        discovery_task = {
            "task_version": DISCOVERY_TASK_VERSION,
            "objective": "提前发现仍来得及参与、正在形成确认的机会",
            "phases": list(DISCOVERY_PHASES),
            "window_mode": "dynamic",
            "window_anchor": due,
            "first_seen_at": None,
            "snapshot_count": 0,
            "last_snapshot_at": observed_at.isoformat() if due else None,
            "candidate_status": "UNOBSERVED" if due else "OUTSIDE_WINDOW",
            "actionability_gate": {
                "required": [
                    "fresh_snapshot",
                    "not_limit_up_or_unfillable",
                    "position_and_odds_defined",
                    "confirmation_and_invalidation_defined",
                ],
                "late_candidate_status": "TOO_LATE",
                "missing_data_status": "RESEARCH_ONLY",
            },
            "handoff": {
                "ace": "判断是否值得承担可定义风险",
                "xiaoyan": "在仍可参与时及时表达确认、失效和放弃条件",
            },
            "audit_fields": [
                "window_id", "observed_at", "source_timestamp", "first_seen_at",
                "snapshot_at", "candidate_status", "sent_at", "too_late_reason",
            ],
        }
        # The window is deliberately incremental: retain an append-only audit
        # row for every observed cycle.  Candidate admission is still owned by
        # ACE/data gates; this ledger only makes discovery timing auditable.
        if due:
            self.discovery_ledger_path.parent.mkdir(parents=True, exist_ok=True)
            prior_rows = []
            try:
                with self.discovery_ledger_path.open("r", encoding="utf-8") as fh:
                    prior_rows = [json.loads(line) for line in fh if line.strip()]
            except (OSError, json.JSONDecodeError):
                prior_rows = []
            day = observed_at.date().isoformat()
            same_day = [r for r in prior_rows if isinstance(r, dict) and r.get("date") == day]
            window_id = f"{day}:{due}"
            row = {
                "schema_version": 1,
                "task_version": DISCOVERY_TASK_VERSION,
                "task_id": "early_opportunity_discovery",
                "window_id": window_id,
                "date": day,
                "observed_at": observed_at.isoformat(),
                "source_timestamp": observed_at.isoformat(),
                "snapshot_at": observed_at.isoformat(),
                "candidate_status": "UNOBSERVED",
                "actionability_status": "DATA_UNAVAILABLE" if status in {"DEGRADED", "RESEARCH_ONLY"} else "PENDING",
                "candidate_count": 0,
                "evidence_refs": self._evidence_refs(),
            }
            if discovery_snapshot is not None:
                candidates = discovery_snapshot.get("candidates", [])
                if not isinstance(candidates, list):
                    candidates = []
                prior_first_seen = {}
                for prior in prior_rows:
                    if not isinstance(prior, dict) or prior.get("date") != day:
                        continue
                    for prior_candidate in prior.get("candidates", []) if isinstance(prior.get("candidates"), list) else []:
                        if not isinstance(prior_candidate, dict):
                            continue
                        symbol = str(prior_candidate.get("symbol", "")).strip()
                        first_seen = str(prior_candidate.get("first_seen_at", "")).strip()
                        if symbol and first_seen and symbol not in prior_first_seen:
                            prior_first_seen[symbol] = first_seen
                normalized_candidates = []
                for candidate in candidates:
                    if not isinstance(candidate, dict):
                        continue
                    normalized = dict(candidate)
                    symbol = str(normalized.get("symbol", "")).strip()
                    normalized["first_seen_at"] = str(
                        normalized.get("first_seen_at") or prior_first_seen.get(symbol) or observed_at.isoformat()
                    )
                    normalized_candidates.append(normalized)
                candidates = normalized_candidates
                snapshot_status = str(discovery_snapshot.get("status", "DATA_UNAVAILABLE")).strip().upper()
                source_timestamp = discovery_snapshot.get("source_timestamp") or observed_at.isoformat()
                row.update({
                    "candidate_status": snapshot_status or "DATA_UNAVAILABLE",
                    "actionability_status": str(
                        discovery_snapshot.get("actionability_status")
                        or ("DATA_UNAVAILABLE" if not candidates else "PENDING")
                    ).upper(),
                    "candidate_count": len(candidates),
                    "candidates": candidates,
                    "snapshot_source": discovery_snapshot.get("source"),
                    "source_timestamp": source_timestamp,
                    "snapshot_source_timestamp": source_timestamp,
                    "snapshot_reason": discovery_snapshot.get("reason"),
                    "snapshot_hash": hashlib.sha256(
                        json.dumps(candidates, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
                    ).hexdigest(),
                })
            with self.discovery_ledger_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            discovery_task["window_id"] = window_id
            discovery_task["snapshot_count"] = len(same_day) + 1
            discovery_task["last_snapshot_at"] = observed_at.isoformat()
            discovery_task["ledger_path"] = str(self.discovery_ledger_path)
            discovery_task["candidate_status"] = row["candidate_status"]
            discovery_task["candidate_count"] = row["candidate_count"]
            discovery_task["first_seen_at"] = min(
                (str(item.get("first_seen_at")) for item in row.get("candidates", []) if isinstance(item, dict) and item.get("first_seen_at")),
                default=None,
            )
            discovery_task["snapshot_source_timestamp"] = row.get("snapshot_source_timestamp")
            discovery_task["snapshot_reason"] = row.get("snapshot_reason")
        counter_evidence = [
            "pytdx/sina 的早盘受控刷新已恢复部分 quote、1m 与 index 观测，但未覆盖全部 Phase 2 操作。",
            "baostock 具备部分日线/5m 可用性却存在一致性缺口；finshare 上游血缘不可观测，不能作为独立交叉验证。",
        ]
        invalidating_conditions = [
            "quote、daily_kline、minute_kline_1m、minute_kline_5m、index 五项均具备生产来源且独立交叉验证后，才可改变当前 DEGRADED。",
            "任一证据过期、覆盖率/字段完整性不足、血缘不可观测或跨源不一致，均使市场状态结论失效。",
        ]
        next_validation = "下一交易观察窗口复跑同一固定股票池与五项核心操作，核对来源血缘、时间戳、覆盖率、字段完整性和一致性。"
        window_record = {
            "observed_at": observed_at.isoformat(),
            "window_status": window_status,
            "finance_status": status,
            "evidence_refs": self._evidence_refs(),
            "data_refresh_attempted": refresh_result is not None,
            "data_refresh": refresh_result,
            "discovery_snapshot": discovery_snapshot,
            "public_sentiment": sentiment_result,
            "market_state": market_state,
            "counter_evidence": counter_evidence,
            "invalidating_conditions": invalidating_conditions,
            "next_validation": next_validation,
            "data_admission_recovery": recovery,
            "early_opportunity_discovery": discovery_task,
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
            "discovery_snapshot": discovery_snapshot,
            "public_sentiment": sentiment_result,
            "market_state": market_state,
            "counter_evidence": counter_evidence,
            "invalidating_conditions": invalidating_conditions,
            "next_validation": next_validation,
            "daily_windows": daily_windows,
            "research_question": (
                "在当前数据准入状态下，哪些金融观察仍可进行，哪些字段缺口阻断实时验证？"
                if due else None
            ),
            "next_action": "record_observation_and_wait_for_independent_evidence" if due else "wait_for_next_window",
            "data_admission_recovery": recovery,
            "cognitive_workstreams": [
                "market_state_research",
                "data_lineage_audit",
                "prediction_review",
                "next_day_hypothesis",
            ] if due else [],
            "early_opportunity_discovery": discovery_task,
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
        temporary = self.report_path.with_name(f".{self.report_path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.report_path)
        return report
