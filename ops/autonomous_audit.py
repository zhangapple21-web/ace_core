import json
import math
import os
import shutil
import statistics
from datetime import datetime, timedelta
from pathlib import Path


READINESS_ORDER = {
    "READY": 0,
    "DEGRADED": 1,
    "RESEARCH_ONLY": 1,
    "WATCH_ONLY": 2,
    "NOT_READY": 2,
    "BLOCKED": 3,
}
TASK_STATES = ("pending", "active", "blocked", "review", "approved", "archived")


def default_paths():
    root = Path(__file__).resolve().parent.parent
    runtime = root / "06_RUNTIME" / "ace" / "data"
    advisor_output = root.parent / "mine-seed" / "05_TOOLS" / "mine_output" / "advisor"
    return {
        "heartbeat": runtime / "memory" / "heartbeat.json",
        "daemon_state": runtime / "memory" / "daemon_state.json",
        "daemon_lock": runtime / "memory" / ".daemon.lock",
        "task_pool": root / "task_pool",
        "data_health": runtime / "stock_data_evidence" / "stock_data_benchmark_latest.json",
        "data_capability_matrix": runtime / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json",
        "advisor_status": advisor_output / "runner_status.json",
        "risk_status": advisor_output / "risk_status.json",
        "provider_watchdog": runtime / "miner_pool" / "provider_watchdog" / "watchdog_state.json",
        "audits": runtime / "audits",
        "environment": {
            "ACE_STOCK_ADVISOR_AUTO_RUN": os.environ.get("ACE_STOCK_ADVISOR_AUTO_RUN"),
            "ACE_STOCK_ADVISOR_AUTO_PUSH": os.environ.get("ACE_STOCK_ADVISOR_AUTO_PUSH"),
            "ACE_TG_ENABLED": os.environ.get("ACE_TG_ENABLED"),
        },
    }


def _read_json(path):
    try:
        with Path(path).open(encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError, json.JSONDecodeError):
        return None, "malformed"


def _parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=None)
    except ValueError:
        return None


def _domain(state, reasons=None, evidence=None, action="continue_observation"):
    return {
        "state": state,
        "reasons": reasons or [],
        "evidence": evidence or [],
        "recommended_action": action,
    }


class AutonomousAudit:
    def __init__(self, paths=None, now=None):
        self.paths = paths or default_paths()
        self.now = now or datetime.now()

    def collect(self):
        tasks = self._load_tasks()
        lifecycle = self._summarize_tasks(tasks)
        fairness = self._summarize_fairness(tasks)
        model_calls = self._summarize_model_calls(tasks)
        production_activity = self._production_activity(model_calls)
        data_health, data_health_domain = self._data_health_summary()
        domains = {
            "runtime": self._runtime_domain(),
            "task_lifecycle": self._task_domain(lifecycle),
            "work_allocation": self._work_allocation_domain(tasks),
            "fairness": self._fairness_domain(fairness),
            "model_task": self._model_task_domain(tasks),
            "miner_pool": self._miner_pool_domain(),
            "shenwen_5_6": self._shenwen_domain("shenwen-5.6", production_activity),
            "shenwen_5_4": self._shenwen_domain("shenwen-5.4", production_activity),
            "data_health": data_health_domain,
            "finance": self._finance_domain(data_health),
            "advisor": self._advisor_domain(),
            "risk": self._risk_domain(),
            "tg": self._telegram_domain(),
        }
        trend = self._trend(lifecycle, fairness, model_calls)
        action = self._recommended_action(domains, trend)
        overall = max((entry["state"] for entry in domains.values()), key=READINESS_ORDER.get)
        return {
            "generated_at": self.now.isoformat(),
            "overall_state": overall,
            "domains": domains,
            "task_lifecycle": lifecycle,
            "fairness": fairness,
            "model_calls": model_calls,
            "production_activity": production_activity,
            "data_health": data_health,
            "trend": trend,
            "recommended_action": action,
        }

    def _load_tasks(self):
        pool = Path(self.paths["task_pool"])
        if not pool.is_dir():
            return []
        records = []
        for path in pool.rglob("RQ-*.json"):
            record, error = _read_json(path)
            if error is None and isinstance(record, dict):
                records.append(record)
        return records

    def _summarize_tasks(self, tasks):
        states = {state: 0 for state in TASK_STATES}
        priorities = {}
        transitions = {"claim": 0, "research": 0, "validation": 0, "rework": 0, "approved": 0, "archive": 0}
        for record in tasks:
            status = record.get("status")
            if status in states:
                states[status] += 1
            priority = record.get("priority", "unknown")
            priorities[priority] = priorities.get(priority, 0) + 1
            for event in record.get("audit_log", []):
                if not isinstance(event, dict):
                    continue
                reason = event.get("reason", "")
                actor = event.get("actor", "")
                target = event.get("to", "")
                if (
                    event.get("event") == "transition"
                    and reason == "lease_claimed"
                    and event.get("from") == "pending"
                    and target == "active"
                ):
                    transitions["claim"] += 1
                if actor == "researcher" and target == "review":
                    transitions["research"] += 1
                if actor == "validator":
                    transitions["validation"] += 1
                if "rework" in str(reason).lower() or record.get("rework_count", 0):
                    transitions["rework"] += 1
                if target == "approved":
                    transitions["approved"] += 1
                if target == "archived":
                    transitions["archive"] += 1
        return {
            "total": len(tasks),
            "states": states,
            "priorities": priorities,
            "backlog": states["pending"] + states["active"] + states["review"],
            "blocked": states["blocked"],
            "transitions": transitions,
        }

    def _summarize_fairness(self, tasks):
        starved = []
        unclaimed = []
        claimed_pending_count = 0
        rework = []
        for record in tasks:
            if record.get("status") != "pending":
                continue
            created = _parse_time(record.get("created_at"))
            if created is None:
                continue
            age_days = (self.now - created).total_seconds() / 86400
            if record.get("last_claimed_at"):
                claimed_pending_count += 1
            else:
                unclaimed.append({
                    "task_id": record.get("task_id"),
                    "priority": record.get("priority"),
                    "source": record.get("creator") or "unknown",
                    "age_hours": max(0.0, age_days * 24),
                })
            outputs = record.get("outputs") if isinstance(record.get("outputs"), dict) else {}
            validator = outputs.get("last_validator_result", {})
            if isinstance(validator, dict) and validator.get("outcome") == "rework_pending":
                hard = validator.get("hard_objections", [])
                hard = hard if isinstance(hard, list) else []
                retry_at = _parse_time(record.get("retry_after"))
                rework.append({
                    "task_id": record.get("task_id"),
                    "hard_objections": [str(item) for item in hard if str(item).strip()],
                    "retry_ready": retry_at is None or retry_at <= self.now,
                })
            threshold = 7 if record.get("priority") in {"critical", "high"} else 14
            if age_days >= threshold:
                starved.append({"task_id": record.get("task_id"), "priority": record.get("priority"), "age_days": round(age_days, 2)})
        ages = sorted(item["age_hours"] for item in unclaimed)
        by_source = {}
        by_priority = {}
        for item in unclaimed:
            by_source[item["source"]] = by_source.get(item["source"], 0) + 1
            priority = item["priority"] or "unknown"
            by_priority[priority] = by_priority.get(priority, 0) + 1
        age_summary = {"oldest": None, "median": None, "p95": None}
        if ages:
            p95_index = max(0, math.ceil(len(ages) * 0.95) - 1)
            age_summary = {
                "oldest": round(ages[-1], 2),
                "median": round(float(statistics.median(ages)), 2),
                "p95": round(ages[p95_index], 2),
            }
        oldest_tasks = sorted(
            unclaimed,
            key=lambda item: (-item["age_hours"], str(item["task_id"])),
        )[:10]
        for item in oldest_tasks:
            item["age_hours"] = round(item["age_hours"], 2)
        hard_objections = {}
        for item in rework:
            for objection in item["hard_objections"]:
                hard_objections[objection] = hard_objections.get(objection, 0) + 1
        all_hard_tasks = sorted(
            item["task_id"] for item in rework if item["hard_objections"]
        )
        all_no_hard_tasks = sorted(
            item["task_id"] for item in rework if not item["hard_objections"]
        )
        hard_tasks = all_hard_tasks[:10]
        no_hard_tasks = all_no_hard_tasks[:10]
        return {
            "starved_count": len(starved),
            "starved_tasks": starved,
            "unclaimed_service_debt": {
                "count": len(unclaimed),
                "claimed_pending_count": claimed_pending_count,
                "age_hours": age_summary,
                "by_source": dict(sorted(by_source.items())),
                "by_priority": dict(sorted(by_priority.items())),
                "oldest_tasks": oldest_tasks,
                "interpretation": "service debt is observable; it is not by itself proof of selector failure",
            },
            "rework_service_debt": {
                "count": len(rework),
                "hard_objection_count": len(all_hard_tasks),
                "no_hard_objection_count": len(all_no_hard_tasks),
                "retry_ready_count": sum(1 for item in rework if item["retry_ready"]),
                "retry_not_due_count": sum(1 for item in rework if not item["retry_ready"]),
                "hard_objections": dict(sorted(hard_objections.items())),
                "representative_task_ids": {
                    "hard_objection": hard_tasks,
                    "no_hard_objection": no_hard_tasks,
                },
                "interpretation": "hard-objection rework requires new evidence; no-hard-objection rework may be completion-ready",
            },
        }

    def _summarize_model_calls(self, tasks):
        result = {
            "HEALTH_PROBE": {"count": 0},
            "CONTROLLED_PROBE": {"count": 0},
            "PRODUCTION_TASK_CALL": {"count": 0, "providers": {}, "selected_models": {}, "api_called": 0, "api_result": {}, "fallback": 0, "trace_complete": 0},
        }
        for record in tasks:
            outputs = record.get("outputs") if isinstance(record.get("outputs"), dict) else {}
            admission = outputs.get("model_task_admission")
            production = (
                isinstance(admission, dict)
                and admission.get("eligible") is True
                and admission.get("classification") in {"reasoning", "strategic", "execution"}
                and f"task_type:{admission.get('classification')}" in record.get("tags", [])
            )
            traces = outputs.get("model_execution", [])
            if not isinstance(traces, list):
                continue
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                bucket = "PRODUCTION_TASK_CALL" if production else "CONTROLLED_PROBE"
                result[bucket]["count"] += 1
                if bucket != "PRODUCTION_TASK_CALL":
                    continue
                self._add_trace(result[bucket], trace)
        watchdog, error = _read_json(self.paths["provider_watchdog"])
        if error is None and isinstance(watchdog, dict):
            result["HEALTH_PROBE"]["count"] = len(watchdog.get("providers", {}))
        return result

    @staticmethod
    def _production_activity(model_calls):
        production = model_calls["PRODUCTION_TASK_CALL"]
        selected_models = production["selected_models"]
        return {
            "MODEL_POOL_PRODUCTION_ACTIVE": production["count"] > 0,
            "SHENWEN_5_6_PRODUCTION_ACTIVE": (
                selected_models.get("gpt-" + "5.6-terra", 0) > 0
                or selected_models.get("shenwen-5.6", 0) > 0
            ),
            "SHENWEN_5_4_PRODUCTION_ACTIVE": (
                selected_models.get("gpt-5.4-mini", 0) > 0
                or selected_models.get("shenwen-5.4", 0) > 0
            ),
        }

    @staticmethod
    def _add_trace(bucket, trace):
        provider = trace.get("provider")
        model = trace.get("selected_model")
        if provider:
            bucket["providers"][provider] = bucket["providers"].get(provider, 0) + 1
        if model:
            bucket["selected_models"][model] = bucket["selected_models"].get(model, 0) + 1
        if trace.get("api_called") is True:
            bucket["api_called"] += 1
        result = trace.get("api_result")
        if result:
            bucket["api_result"][result] = bucket["api_result"].get(result, 0) + 1
        if trace.get("fallback") is True:
            bucket["fallback"] += 1
        if trace.get("trace_complete") is True:
            bucket["trace_complete"] += 1

    def _runtime_domain(self):
        heartbeat, heartbeat_error = _read_json(self.paths["heartbeat"])
        state, state_error = _read_json(self.paths["daemon_state"])
        lock, lock_error = _read_json(self.paths["daemon_lock"])
        evidence = [str(self.paths[name]) for name in ("heartbeat", "daemon_state", "daemon_lock")]
        if heartbeat_error or state_error or lock_error:
            return _domain("NOT_READY", ["runtime_evidence_missing_or_malformed"], evidence, "repair_runtime_observation_evidence")
        last_beat = _parse_time(heartbeat.get("last_beat"))
        if last_beat is None or self.now - last_beat > timedelta(minutes=30):
            return _domain("NOT_READY", ["heartbeat_stale"], evidence, "inspect_daemon_runtime")
        if heartbeat.get("pid") != lock.get("pid"):
            return _domain("BLOCKED", ["daemon_lock_pid_mismatch"], evidence, "repair_daemon_lock_conflict")
        return _domain("READY", evidence=evidence)

    def _task_domain(self, lifecycle):
        # ``blocked`` is a deliberate quarantine state, not proof that the
        # lifecycle itself is unable to make progress.  Keep its count and
        # trend visible, but do not turn valid per-task containment into a
        # global production blocker.
        return _domain("READY", evidence=[str(self.paths["task_pool"])])

    def _work_allocation_domain(self, tasks):
        evidence = [str(self.paths["task_pool"])]
        if not tasks:
            return _domain("NOT_READY", ["work_allocation_evidence_unavailable"], evidence, "restore_work_allocation_evidence")
        return _domain("READY", evidence=evidence)

    def _fairness_domain(self, fairness):
        if fairness["starved_count"]:
            return _domain("BLOCKED", ["task_starvation_detected"], [str(self.paths["task_pool"])], "resolve_task_starvation")
        return _domain("READY", evidence=[str(self.paths["task_pool"])])

    def _model_task_domain(self, tasks):
        evidence = [str(self.paths["task_pool"])]
        if any(isinstance(record.get("outputs", {}).get("model_task_admission"), dict) for record in tasks):
            return _domain("READY", evidence=evidence)
        return _domain("NOT_READY", ["model_task_admission_evidence_unavailable"], evidence, "restore_model_task_evidence")

    def _miner_pool_domain(self):
        watchdog, error = _read_json(self.paths["provider_watchdog"])
        evidence = [str(self.paths["provider_watchdog"])]
        if error or not isinstance(watchdog, dict):
            return _domain("NOT_READY", ["miner_pool_evidence_missing_or_malformed"], evidence, "restore_miner_pool_evidence")
        if any(record.get("status") in {"BLOCKED", "FAILED"} for record in watchdog.get("providers", {}).values() if isinstance(record, dict)):
            return _domain("BLOCKED", ["miner_pool_persisted_failure"], evidence, "inspect_miner_pool_failure")
        return _domain("READY", evidence=evidence)

    @staticmethod
    def _shenwen_domain(model, production_activity):
        active = production_activity["SHENWEN_5_6_PRODUCTION_ACTIVE"] if model == "shenwen-5.6" else production_activity["SHENWEN_5_4_PRODUCTION_ACTIVE"]
        if active:
            return _domain("READY", evidence=["PRODUCTION_TASK_CALL", model])
        return _domain("NOT_READY", ["production_task_call_unverified"], ["PRODUCTION_TASK_CALL", model], "continue_production_observation")

    def _data_health_summary(self):
        data, error = _read_json(self.paths["data_health"])
        path = str(self.paths["data_health"])
        if error:
            return {"sources": {}, "evidence_error": error}, _domain(
                "NOT_READY",
                ["data_health_evidence_missing_or_malformed"],
                [path],
                "restore_data_health_evidence",
            )
        summary = data.get("summary", {}) if isinstance(data, dict) else {}
        sources = summary.get("sources", {}) if isinstance(summary, dict) else {}
        metrics = {}
        degraded = []
        for source, record in sources.items():
            if not isinstance(record, dict):
                continue
            metrics[source] = {
                key: record.get(key)
                for key in ("availability", "field_completeness", "coverage", "consistency")
            }
            if any(isinstance(value, (int, float)) and value < 0.8 for value in metrics[source].values()):
                degraded.append(source)
        if not metrics:
            return {"sources": {}, "degraded_sources": []}, _domain(
                "NOT_READY",
                ["data_health_metrics_unavailable"],
                [path],
                "restore_data_health_evidence",
            )
        matrix_path = Path(self.paths.get(
            "data_capability_matrix",
            Path(self.paths["data_health"]).with_name("A_SHARE_DATA_CAPABILITY_MATRIX.json"),
        ))
        matrix, matrix_error = _read_json(matrix_path)
        evidence = [path, str(matrix_path)]
        result = {
            "sources": metrics,
            "degraded_sources": degraded,
            "observation_rounds": data.get("rounds"),
            "admission_status": None,
        }
        if matrix_error or not isinstance(matrix, dict):
            return result, _domain(
                "NOT_READY",
                ["data_capability_matrix_missing_or_malformed"],
                evidence,
                "restore_data_capability_evidence",
            )
        admission = matrix.get("phase_two_admission", {})
        operations = admission.get("core_operations", {}) if isinstance(admission, dict) else {}
        result["admission_status"] = admission.get("status") if isinstance(admission, dict) else None
        required_operations = {"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"}
        strictly_admitted = (
            result["admission_status"] == "ADMITTED"
            and set(operations) == required_operations
            and all(
                isinstance(operations.get(name), dict)
                and bool(operations[name].get("production_sources"))
                and len(set(operations[name].get("independence_groups", []))) >= 2
                and operations[name].get("has_independent_cross_validation") is True
                for name in required_operations
            )
        )
        if not strictly_admitted:
            return result, _domain(
                "BLOCKED",
                ["a_share_data_not_admitted"],
                evidence,
                "resolve_data_admission_blockers",
            )
        rounds = data.get("rounds")
        if not isinstance(rounds, int) or rounds < 5:
            return result, _domain(
                "NOT_READY",
                ["data_health_observation_window_insufficient"],
                evidence,
                "run_bounded_multi_round_data_observation",
            )
        return result, _domain("READY", evidence=evidence)

    def _finance_domain(self, data_health):
        """Expose application readiness without weakening the data gate.

        A failed production admission blocks transaction-grade recommendation,
        but it must not erase research work when a subset of core operations is
        independently usable.
        """
        matrix_path = Path(self.paths.get(
            "data_capability_matrix",
            Path(self.paths["data_health"]).with_name("A_SHARE_DATA_CAPABILITY_MATRIX.json"),
        ))
        matrix, error = _read_json(matrix_path)
        evidence = [str(self.paths["data_health"]), str(matrix_path)]
        if error or not isinstance(matrix, dict):
            return _domain("NOT_READY", ["finance_capability_evidence_unavailable"], evidence, "continue_watch_only")
        operations = matrix.get("phase_two_admission", {}).get("core_operations", {})
        required = {"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"}
        admitted = {
            name for name in required
            if isinstance(operations.get(name), dict)
            and operations[name].get("production_sources")
            and operations[name].get("has_independent_cross_validation") is True
        }
        if admitted == required:
            return _domain("READY", evidence=evidence)
        if admitted:
            return _domain("DEGRADED", ["partial_core_operation_admission"], evidence, "continue_financial_research_only")
        if data_health.get("observation_rounds"):
            return _domain("RESEARCH_ONLY", ["no_core_operation_fully_admitted"], evidence, "continue_source_and_historical_research")
        return _domain("WATCH_ONLY", ["finance_observation_not_started"], evidence, "continue_watch_only")

    def _advisor_domain(self):
        advisor, error = _read_json(self.paths["advisor_status"])
        evidence = [str(self.paths["advisor_status"])]
        if error or not isinstance(advisor, dict):
            return _domain("NOT_READY", ["advisor_evidence_missing_or_malformed"], evidence, "restore_advisor_evidence")
        if advisor.get("last_run_success") is False:
            return _domain("BLOCKED", ["advisor_persisted_failure"], evidence, "inspect_advisor_failure")
        return _domain("READY", evidence=evidence)

    def _risk_domain(self):
        risk, error = _read_json(self.paths["risk_status"])
        evidence = [str(self.paths["risk_status"])]
        if error or not isinstance(risk, dict):
            return _domain("NOT_READY", ["risk_evidence_missing_or_malformed"], evidence, "restore_risk_evidence")
        if risk.get("status") in {"blocked", "failed"}:
            return _domain("BLOCKED", ["risk_persisted_failure"], evidence, "inspect_risk_failure")
        return _domain("READY", evidence=evidence)

    def _telegram_domain(self):
        values = self.paths.get("environment", {})
        unknown = [name for name, value in values.items() if value is None]
        if unknown:
            return _domain("NOT_READY", ["automation_or_telegram_state_unavailable"], unknown, "record_automation_and_telegram_state")
        return _domain("READY", evidence=list(values))

    def _trend(self, lifecycle, fairness, model_calls):
        history = self._history_reports()
        anomalies = []
        previous = history[-1] if history else None
        if previous:
            old_lifecycle = previous.get("task_lifecycle", {})
            if lifecycle["backlog"] > old_lifecycle.get("backlog", lifecycle["backlog"]):
                anomalies.append("backlog_increasing")
            if lifecycle["blocked"] > old_lifecycle.get("blocked", lifecycle["blocked"]):
                anomalies.append("blocked_tasks_increasing")
            if fairness["starved_count"] > previous.get("fairness", {}).get("starved_count", fairness["starved_count"]):
                anomalies.append("starvation_increasing")
        return {"history_days": len(history), "anomalies": anomalies, "production_task_calls": model_calls["PRODUCTION_TASK_CALL"]["count"]}

    def _history_reports(self):
        root = Path(self.paths["audits"]) / "history"
        if not root.is_dir():
            return []
        reports = []
        for path in sorted(root.glob("*")):
            report, error = _read_json(path / "daily_health.json")
            if error is None and isinstance(report, dict):
                reports.append(report)
        return reports

    @staticmethod
    def _recommended_action(domains, trend):
        for name, domain in domains.items():
            if domain["state"] == "BLOCKED":
                return {"code": domain["recommended_action"], "domain": name}
        for name, domain in domains.items():
            if domain["state"] == "NOT_READY":
                return {"code": domain["recommended_action"], "domain": name}
        if trend["anomalies"]:
            return {"code": "investigate_adverse_trend", "domain": "trend"}
        return {"code": "continue_normal_observation", "domain": "overall"}

    def write_reports(self, report):
        audit_root = Path(self.paths["audits"])
        audit_root.mkdir(parents=True, exist_ok=True)
        blocking = {name: domain for name, domain in report["domains"].items() if domain["state"] != "READY"}
        outputs = {
            "daily_health.json": report,
            "blocking_reasons.json": {"generated_at": report["generated_at"], "overall_state": report["overall_state"], "blocking_reasons": blocking, "recommended_action": report["recommended_action"]},
            "trend_report.json": {"generated_at": report["generated_at"], "trend": report["trend"], "recommended_action": report["recommended_action"]},
        }
        for filename, payload in outputs.items():
            (audit_root / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        (audit_root / "daily_health.md").write_text(self._markdown(report), encoding="utf-8")
        history = audit_root / "history" / self.now.date().isoformat()
        history.mkdir(parents=True, exist_ok=True)
        for filename, payload in outputs.items():
            (history / filename).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self._prune_history(audit_root / "history")
        return {"written": {"daily_health.json", "daily_health.md", "blocking_reasons.json", "trend_report.json"}, "report": report}

    @staticmethod
    def _markdown(report):
        lines = ["# ACE Daily Health", "", f"Overall: `{report['overall_state']}`", "", "## Domains"]
        lines.extend(f"- {name}: `{domain['state']}`" for name, domain in report["domains"].items())
        lines.extend(["", "## Recommended Action", "", f"`{report['recommended_action']['code']}`"])
        return "\n".join(lines) + "\n"

    def _prune_history(self, history_root):
        if not history_root.is_dir():
            return
        cutoff = self.now.date() - timedelta(days=90)
        for child in history_root.iterdir():
            try:
                date = datetime.fromisoformat(child.name).date()
            except ValueError:
                continue
            if child.is_dir() and date < cutoff:
                shutil.rmtree(child)


def run_audit(paths=None):
    audit = AutonomousAudit(paths)
    return audit.write_reports(audit.collect())
