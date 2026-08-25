"""Evidence-only daily growth ledger for the existing ACE lifecycle."""

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class DailyGrowthLedger:
    def __init__(
        self,
        task_pool,
        report_path: str,
        observations_path: Optional[str] = None,
        model_work_discovery_path: Optional[str] = None,
    ):
        self.task_pool = task_pool
        self.report_path = Path(report_path)
        self.observations_path = (
            Path(observations_path)
            if observations_path
            else self.report_path.parent / "observations" / "observations.jsonl"
        )
        self.model_work_discovery_path = (
            Path(model_work_discovery_path)
            if model_work_discovery_path
            else self.report_path.parent / "model_work_discovery_latest.json"
        )

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _observations_for_day(path: Path, day: str) -> List[Dict[str, Any]]:
        observations = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return observations
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(value, dict)
                and str(value.get("created_at", "")).startswith(day)
            ):
                observations.append(value)
        return observations

    @staticmethod
    def _model_classification(task) -> str:
        outputs = task.outputs if isinstance(task.outputs, dict) else {}
        admission = outputs.get("model_task_admission", {})
        if not isinstance(admission, dict) or admission.get("eligible") is not True:
            return ""
        classification = str(admission.get("classification", "")).lower()
        return classification if classification in {"reasoning", "strategic", "execution"} else ""

    @staticmethod
    def _first_claim_at(task) -> Optional[str]:
        claims = [
            str(event.get("at", ""))
            for event in task.audit_log or []
            if (
                isinstance(event, dict)
                and event.get("event") == "transition"
                and event.get("from") == "pending"
                and event.get("to") == "active"
                and event.get("reason") == "lease_claimed"
                and event.get("at")
            )
        ]
        return min(claims) if claims else None

    @staticmethod
    def _seconds_between(start: str, end: str) -> Optional[float]:
        try:
            start_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_at = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return max(0.0, (end_at - start_at).total_seconds())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> Optional[float]:
        return round(numerator / denominator, 4) if denominator else None

    @staticmethod
    def _count(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _latency_summary(values: List[float]) -> Dict[str, Any]:
        if not values:
            return {"count": 0, "median": None, "p95": None}
        ordered = sorted(values)
        p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
        return {
            "count": len(ordered),
            "median": round(float(statistics.median(ordered)), 3),
            "p95": round(float(ordered[p95_index]), 3),
        }

    @classmethod
    def _model_performance(cls, tasks: List[Any], day: str) -> Dict[str, Any]:
        """Aggregate production traces without influencing model routing."""
        groups: Dict[Any, Dict[str, Any]] = {}
        production_call_count = 0
        for task in tasks:
            outputs = task.outputs if isinstance(task.outputs, dict) else {}
            admission = outputs.get("model_task_admission", {})
            if not isinstance(admission, dict) or admission.get("eligible") is not True:
                continue
            validator = outputs.get("last_validator_result", {})
            validator_outcome = (
                str(validator.get("outcome", ""))
                if isinstance(validator, dict)
                else ""
            )
            traces = outputs.get("model_execution", [])
            if not isinstance(traces, list):
                continue
            task_groups = set()
            for trace in traces:
                if (
                    not isinstance(trace, dict)
                    or trace.get("api_called") is not True
                    or not str(trace.get("at", "")).startswith(day)
                ):
                    continue
                key = (
                    str(trace.get("task_type") or admission.get("classification") or "unknown"),
                    str(trace.get("provider") or "unknown"),
                    str(trace.get("selected_model") or trace.get("model") or "unknown"),
                )
                group = groups.setdefault(key, {
                    "calls": 0,
                    "successful_calls": 0,
                    "fallback_calls": 0,
                    "latencies": [],
                    "known_costs": [],
                    "unknown_costs": 0,
                    "currency": "",
                    "task_ids": set(),
                    "assessed_task_ids": set(),
                    "accepted_task_ids": set(),
                })
                production_call_count += 1
                group["calls"] += 1
                trace_result = trace.get("result", trace.get("api_result"))
                if trace_result == "success":
                    group["successful_calls"] += 1
                if trace.get("fallback") is True:
                    group["fallback_calls"] += 1
                latency = trace.get("latency_ms")
                if isinstance(latency, (int, float)) and not isinstance(latency, bool):
                    group["latencies"].append(float(latency))
                cost = trace.get("cost", {})
                total_cost = cost.get("total_usd") if isinstance(cost, dict) else None
                if isinstance(total_cost, (int, float)) and not isinstance(total_cost, bool):
                    group["known_costs"].append(float(total_cost))
                    currency = str(cost.get("currency") or "USD")
                    if group["currency"] and group["currency"] != currency:
                        group["currency"] = "MIXED"
                    elif not group["currency"]:
                        group["currency"] = currency
                else:
                    group["unknown_costs"] += 1
                group["task_ids"].add(task.task_id)
                task_groups.add(key)
            for key in task_groups:
                if validator_outcome:
                    groups[key]["assessed_task_ids"].add(task.task_id)
                if validator_outcome == "approved":
                    groups[key]["accepted_task_ids"].add(task.task_id)

        result_groups = []
        for (task_type, provider, model), group in sorted(groups.items()):
            latencies = sorted(group["latencies"])
            p95_index = max(0, math.ceil(len(latencies) * 0.95) - 1) if latencies else 0
            assessed = len(group["assessed_task_ids"])
            accepted = len(group["accepted_task_ids"])
            result_groups.append({
                "task_type": task_type,
                "provider": provider,
                "model": model,
                "sample_count": group["calls"],
                "successful_call_count": group["successful_calls"],
                "success_rate": cls._ratio(group["successful_calls"], group["calls"]),
                "fallback_call_count": group["fallback_calls"],
                "fallback_rate": cls._ratio(group["fallback_calls"], group["calls"]),
                "latency_ms": {
                    "count": len(latencies),
                    "average": round(sum(latencies) / len(latencies), 3) if latencies else None,
                    "p95": round(latencies[p95_index], 3) if latencies else None,
                },
                "cost": {
                    "currency": group["currency"] or "USD",
                    "known_call_count": len(group["known_costs"]),
                    "unknown_call_count": group["unknown_costs"],
                    "total": round(sum(group["known_costs"]), 8),
                },
                "validator": {
                    "task_count": len(group["task_ids"]),
                    "assessed_task_count": assessed,
                    "accepted_task_count": accepted,
                    "accept_rate": cls._ratio(accepted, assessed),
                },
            })
        return {
            "schema_version": 1,
            "date": day,
            "shadow_only": True,
            "routing_effect": False,
            "health_probes_excluded": True,
            "production_call_count": production_call_count,
            "group_count": len(result_groups),
            "groups": result_groups,
            "coverage": {
                "source": "admitted_task_model_execution_traces",
                "validator_attribution": "latest_task_outcome",
                "cost_unknown_is_not_zero": True,
            },
        }

    def _finance_status(self) -> str:
        matrix_path = self.report_path.parent / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
        try:
            matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "NOT_READY"
        operations = matrix.get("phase_two_admission", {}).get("core_operations", {})
        required = {"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"}
        admitted = {
            name for name in required
            if isinstance(operations.get(name), dict)
            and operations[name].get("production_sources")
            and operations[name].get("has_independent_cross_validation") is True
        }
        if admitted == required:
            return "FULL_READY"
        if admitted:
            return "DEGRADED"
        return "RESEARCH_ONLY"

    @staticmethod
    def _window_status(
        observations: int,
        candidates: int,
        eligible: int,
        rejected: int,
        deferred: int,
        eligible_but_unserved: int,
        model_calls: int,
    ) -> str:
        if model_calls:
            return "MODEL_WORK_SERVICED"
        if eligible_but_unserved:
            return "ELIGIBLE_WORK_NOT_SERVICED"
        if observations == 0:
            return "OBSERVATION_PIPELINE_SILENT"
        if candidates == 0:
            return "NO_CANDIDATE_DISCOVERED"
        if eligible == 0 and rejected:
            return "CANDIDATE_FOUND_BUT_REJECTED"
        if deferred:
            return "CANDIDATE_DEFERRED"
        if eligible:
            return "ELIGIBLE_WORK_SERVICE_INCOMPLETE"
        return "NO_VALUABLE_WORK"

    def build(self, day: Optional[str] = None) -> Dict[str, Any]:
        date = day or datetime.now().date().isoformat()
        previous_report = self._read_json(self.report_path)
        observations = self._observations_for_day(self.observations_path, date)
        discovery = self._read_json(self.model_work_discovery_path)
        discovery_matches_day = discovery.get("discovery_date") == date
        funnel = (
            discovery.get("admission_funnel", {})
            if discovery_matches_day and isinstance(discovery.get("admission_funnel"), dict)
            else {}
        )
        candidate_work = self._count(funnel.get("candidate_count", 0))
        if (
            discovery_matches_day
            and not funnel
            and discovery.get("outcome") == "MODEL_WORK_CANDIDATE_OBSERVED"
        ):
            candidate_work = 1
        admitted_candidate_work = self._count(funnel.get("eligible_count", 0))
        rejected_work = self._count(funnel.get("rejected_count", 0))
        deferred_work = max(
            0, candidate_work - admitted_candidate_work - rejected_work
        )
        archived = []
        model_tasks = set()
        production_calls = []
        tasks_created_today = []
        model_work_by_type = {"reasoning": 0, "strategic": 0, "execution": 0}
        financial_research_work = 0
        served_model_work = 0
        service_latencies = []
        all_tasks = self.task_pool.list_tasks(limit=10000)
        for task in all_tasks:
            outputs = task.outputs if isinstance(task.outputs, dict) else {}
            admission = outputs.get("model_task_admission", {})
            is_model = isinstance(admission, dict) and admission.get("eligible") is True
            if str(task.created_at).startswith(date):
                tasks_created_today.append(task)
                task_text = " ".join(str(value).lower() for value in (
                    task.title, task.creator, *(task.tags or []),
                ))
                if any(marker in task_text for marker in ("financial", "a_share", "stock", "金融", "a股")):
                    financial_research_work += 1
                classification = self._model_classification(task)
                if classification:
                    model_work_by_type[classification] += 1
                    claimed_at = self._first_claim_at(task)
                    if claimed_at:
                        served_model_work += 1
                        latency = self._seconds_between(task.created_at, claimed_at)
                        if latency is not None:
                            service_latencies.append(latency)
            for event in task.audit_log or []:
                if (
                    isinstance(event, dict)
                    and event.get("event") == "transition"
                    and event.get("to") == "archived"
                    and str(event.get("at", "")).startswith(date)
                ):
                    archived.append(task.task_id)
                    if is_model:
                        model_tasks.add(task.task_id)
            for trace in outputs.get("model_execution", []) if isinstance(outputs.get("model_execution", []), list) else []:
                if (
                    is_model
                    and isinstance(trace, dict)
                    and str(trace.get("at", "")).startswith(date)
                    and trace.get("api_called") is True
                    and trace.get("api_result") == "success"
                ):
                    production_calls.append({
                        "task_id": task.task_id,
                        "task_type": trace.get("task_type"),
                        "provider": trace.get("provider"),
                        "selected_model": trace.get("selected_model"),
                        "response_sha256": trace.get("response_sha256"),
                        "at": trace.get("at"),
                    })
        accepted_work = len(tasks_created_today)
        admitted_model_tasks_today = sum(model_work_by_type.values())
        accepted_model_work = admitted_model_tasks_today
        eligible_model_supply = max(accepted_model_work, admitted_candidate_work)
        eligible_but_unserved = max(0, eligible_model_supply - served_model_work)
        local_work = max(0, accepted_work - admitted_model_tasks_today)
        window_status = self._window_status(
            len(observations),
            candidate_work,
            eligible_model_supply,
            rejected_work,
            deferred_work,
            eligible_but_unserved,
            len(production_calls),
        )
        history = previous_report.get("cognitive_work_supply_history", [])
        history = [dict(item) for item in history if isinstance(item, dict)]
        history = [item for item in history if item.get("date") != date]
        history.append({
            "date": date,
            "discovery_window_recorded": discovery_matches_day,
            "observations": len(observations),
            "candidate_work": candidate_work,
            "window_status": window_status,
        })
        history = sorted(history, key=lambda item: str(item.get("date", "")))[-14:]
        consecutive_no_candidate_windows = 0
        for item in reversed(history):
            if (
                item.get("discovery_window_recorded") is True
                and self._count(item.get("candidate_work", 0)) == 0
            ):
                consecutive_no_candidate_windows += 1
                continue
            break
        if len(observations) == 0:
            discovery_health = "OBSERVATION_PIPELINE_SILENT"
        elif consecutive_no_candidate_windows >= 3:
            discovery_health = "INVESTIGATE_DISCOVERY_CHAIN"
        elif candidate_work == 0:
            discovery_health = "WATCH"
        else:
            discovery_health = "HEALTHY"
        cognitive_work_supply = {
            "schema_version": 1,
            "date": date,
            "observations": len(observations),
            "candidate_work": candidate_work,
            "accepted_work": accepted_work,
            "accepted_model_work": accepted_model_work,
            "admitted_candidate_work": admitted_candidate_work,
            "local_work": local_work,
            "reasoning_work": model_work_by_type["reasoning"],
            "strategic_work": model_work_by_type["strategic"],
            "execution_work": model_work_by_type["execution"],
            "financial_research_work": financial_research_work,
            "deferred_work": deferred_work,
            "rejected_work": rejected_work,
            "eligible_but_unserved": eligible_but_unserved,
            "model_calls": len(production_calls),
            "archived_work": len(set(archived)),
            "discovery_yield": self._ratio(candidate_work, len(observations)),
            "admission_rejection_rate": self._ratio(rejected_work, candidate_work),
            "service_latency_seconds": self._latency_summary(service_latencies),
            "model_work_service_rate": self._ratio(
                served_model_work, eligible_model_supply
            ),
            "window_status": window_status,
            "consecutive_no_candidate_windows": consecutive_no_candidate_windows,
            "discovery_health": discovery_health,
            "activity_quota_enforced": False,
            "model_call_quota_enforced": False,
            "coverage": {
                "complete": False,
                "observations": "runtime_observer_retained_window",
                "candidate_work": "model_work_discovery_only",
                "accepted_work": "taskpool_created_today",
                "missing_candidate_funnels": [
                    "daily_learning",
                    "local_observer",
                    "file_scanner",
                    "mine_seed_scanner",
                ],
            },
        }
        report = {
            "schema_version": 1,
            "date": date,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "outcome": (
                "MEASURABLE_GROWTH"
                if archived or production_calls
                else "NO_MEASURABLE_GROWTH"
            ),
            "archived_task_count": len(set(archived)),
            "archived_task_ids": sorted(set(archived)),
            "archived_model_task_count": len(model_tasks),
            "archived_model_task_ids": sorted(model_tasks),
            "production_model_call_count": len(production_calls),
            "production_model_calls": production_calls,
            "model_performance_ledger": self._model_performance(all_tasks, date),
            "health_probes_excluded": True,
            "no_growth_quota": True,
            "finance_status": self._finance_status(),
            "cognitive_work_supply": cognitive_work_supply,
            "cognitive_work_supply_history": history,
        }
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.report_path)
        return report
