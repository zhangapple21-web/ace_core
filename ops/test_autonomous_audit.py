import hashlib
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.autonomous_audit import AutonomousAudit, run_audit


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def audit_paths(root):
    runtime = root / "runtime"
    return {
        "heartbeat": runtime / "memory" / "heartbeat.json",
        "daemon_state": runtime / "memory" / "daemon_state.json",
        "daemon_lock": runtime / "memory" / ".daemon.lock",
        "task_pool": root / "task_pool",
        "data_health": runtime / "stock_data_evidence" / "stock_data_benchmark_latest.json",
        "data_capability_matrix": runtime / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json",
        "advisor_status": root / "advisor" / "output" / "runner_status.json",
        "risk_status": root / "advisor" / "output" / "risk_status.json",
        "provider_watchdog": runtime / "miner_pool" / "provider_watchdog" / "watchdog_state.json",
        "audits": runtime / "audits",
        "environment": {},
    }


def task(task_id, status="pending", priority="medium", outputs=None, tags=None, created_at=None, **extra):
    return {
        "task_id": task_id,
        "title": task_id,
        "status": status,
        "priority": priority,
        "tags": tags or [],
        "outputs": outputs or {},
        "created_at": created_at or datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "audit_log": extra.pop("audit_log", []),
        **extra,
    }


def write_task(pool, record):
    task_id = record["task_id"]
    if not task_id.startswith("RQ-"):
        task_id = f"RQ-{task_id}"
        record["task_id"] = task_id
    write_json(pool / record["status"] / f"{task_id}.json", record)


def source_hashes(paths):
    digests = {}
    for name, path in paths.items():
        if isinstance(path, Path) and path.exists() and path.is_file():
            digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    for path in paths["task_pool"].rglob("*.json"):
        digests[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def tree_hashes(root, excluded=None):
    excluded = excluded or set()
    digests = {}
    for path in root.rglob("*"):
        if path.is_file() and not any(path.is_relative_to(directory) for directory in excluded):
            digests[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def test_production_trace_requires_admitted_reasoning_task(tmp_path):
    paths = audit_paths(tmp_path)
    admitted = {
        "model_task_admission": {"eligible": True, "classification": "reasoning"},
        "model_execution": [{
            "provider": "shenwen",
            "selected_model": "shenwen-5.6",
            "api_called": True,
            "api_result": "success",
            "fallback": False,
            "trace_complete": True,
        }],
    }
    write_task(paths["task_pool"], task("admitted", outputs=admitted, tags=["task_type:reasoning"]))
    write_task(paths["task_pool"], task("rejected", outputs={
        "model_task_admission": {"eligible": False, "classification": "reasoning"},
        "model_execution": [{"selected_model": "shenwen-5.4", "api_called": True}],
    }, tags=["task_type:reasoning"]))
    write_json(paths["provider_watchdog"], {"providers": {"shenwen": {"status": "HEALTHY"}}})

    report = AutonomousAudit(paths).collect()

    assert report["model_calls"]["PRODUCTION_TASK_CALL"]["count"] == 1
    assert report["model_calls"]["PRODUCTION_TASK_CALL"]["selected_models"] == {"shenwen-5.6": 1}
    assert report["model_calls"]["HEALTH_PROBE"]["count"] == 1
    assert report["model_calls"]["CONTROLLED_PROBE"]["count"] == 1
    assert report["production_activity"] == {
        "MODEL_POOL_PRODUCTION_ACTIVE": True,
        "SHENWEN_5_6_PRODUCTION_ACTIVE": True,
        "SHENWEN_5_4_PRODUCTION_ACTIVE": False,
    }


def test_production_activity_excludes_health_and_controlled_probes(tmp_path):
    paths = audit_paths(tmp_path)
    write_task(paths["task_pool"], task("controlled", outputs={
        "model_task_admission": {"eligible": False, "classification": "reasoning"},
        "model_execution": [{"selected_model": "shenwen-5.6", "api_called": True}],
    }, tags=["task_type:reasoning"]))
    write_json(paths["provider_watchdog"], {"providers": {"shenwen": {"status": "HEALTHY"}}})

    report = AutonomousAudit(paths).collect()

    assert report["model_calls"]["HEALTH_PROBE"]["count"] == 1
    assert report["model_calls"]["CONTROLLED_PROBE"]["count"] == 1
    assert report["model_calls"]["PRODUCTION_TASK_CALL"]["count"] == 0
    assert report["production_activity"] == {
        "MODEL_POOL_PRODUCTION_ACTIVE": False,
        "SHENWEN_5_6_PRODUCTION_ACTIVE": False,
        "SHENWEN_5_4_PRODUCTION_ACTIVE": False,
    }


def test_readonly_report_exposes_each_required_observation_domain(tmp_path):
    paths = audit_paths(tmp_path)
    write_json(paths["provider_watchdog"], {"providers": {"shenwen": {"status": "HEALTHY"}}})
    write_task(paths["task_pool"], task("allocated", audit_log=[{
        "actor": "allocator",
        "reason": "selected",
    }], outputs={"model_task_admission": {"eligible": False, "classification": "reasoning"}}))

    report = AutonomousAudit(paths).collect()

    assert set(report["domains"]) == {
        "runtime",
        "task_lifecycle",
        "work_allocation",
        "fairness",
        "model_task",
        "miner_pool",
        "shenwen_5_6",
        "shenwen_5_4",
        "data_health",
        "advisor",
        "risk",
        "tg",
    }
    assert report["domains"]["work_allocation"]["evidence"] == [str(paths["task_pool"])]
    assert report["domains"]["model_task"]["evidence"] == [str(paths["task_pool"])]
    assert report["domains"]["miner_pool"]["state"] == "READY"
    assert report["domains"]["shenwen_5_6"]["state"] == "NOT_READY"
    assert report["domains"]["shenwen_5_4"]["state"] == "NOT_READY"
    assert report["domains"]["advisor"]["state"] == "NOT_READY"
    assert report["domains"]["risk"]["state"] == "NOT_READY"


def test_quarantined_blocked_tasks_do_not_block_taskpool_health(tmp_path):
    paths = audit_paths(tmp_path)
    write_task(paths["task_pool"], task(
        "waiting-for-new-evidence",
        status="blocked",
        blocked_reason="waiting for independent external evidence",
    ))

    report = AutonomousAudit(paths).collect()

    assert report["task_lifecycle"]["blocked"] == 1
    assert report["domains"]["task_lifecycle"] == {
        "state": "READY",
        "reasons": [],
        "evidence": [str(paths["task_pool"])],
        "recommended_action": "continue_observation",
    }


def test_data_health_uses_strict_admission_not_rejected_candidate_metrics(tmp_path):
    paths = audit_paths(tmp_path)
    write_json(paths["data_health"], {
        "rounds": 5,
        "summary": {"sources": {
            "production": {"availability": 1.0, "field_completeness": 1.0, "coverage": 1.0, "consistency": 1.0},
            "rejected": {"availability": 0.0, "field_completeness": 0.0, "coverage": 0.0, "consistency": 0.0},
        }},
    })
    operations = {
        name: {
            "production_sources": ["source-a", "source-b"],
            "independence_groups": ["group-a", "group-b"],
            "has_independent_cross_validation": True,
        }
        for name in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")
    }
    write_json(paths["data_capability_matrix"], {
        "phase_two_admission": {"status": "ADMITTED", "core_operations": operations},
    })

    report = AutonomousAudit(paths).collect()

    assert report["data_health"]["degraded_sources"] == ["rejected"]
    assert report["domains"]["data_health"]["state"] == "READY"


def test_data_health_does_not_admit_a_single_round_success(tmp_path):
    paths = audit_paths(tmp_path)
    write_json(paths["data_health"], {
        "rounds": 1,
        "summary": {"sources": {
            "source-a": {"availability": 1.0, "field_completeness": 1.0, "coverage": 1.0, "consistency": 1.0},
        }},
    })
    operations = {
        name: {
            "production_sources": ["source-a", "source-b"],
            "independence_groups": ["group-a", "group-b"],
            "has_independent_cross_validation": True,
        }
        for name in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")
    }
    write_json(paths["data_capability_matrix"], {
        "phase_two_admission": {"status": "ADMITTED", "core_operations": operations},
    })

    report = AutonomousAudit(paths).collect()

    assert report["domains"]["data_health"]["state"] == "NOT_READY"
    assert report["domains"]["data_health"]["reasons"] == ["data_health_observation_window_insufficient"]


def test_missing_runtime_is_not_ready_and_backlog_growth_is_anomaly(tmp_path):
    paths = audit_paths(tmp_path)
    old = (datetime.now() - timedelta(days=8)).isoformat()
    write_task(paths["task_pool"], task("old-high", priority="high", created_at=old))
    write_task(paths["task_pool"], task("current-medium"))
    write_task(paths["task_pool"], task("current-low", priority="low"))
    write_json(paths["audits"] / "history" / "2026-08-23" / "daily_health.json", {
        "task_lifecycle": {"backlog": 1, "blocked": 0},
        "fairness": {"starved_count": 0},
    })
    write_json(paths["audits"] / "history" / "2026-08-24" / "daily_health.json", {
        "task_lifecycle": {"backlog": 2, "blocked": 0},
        "fairness": {"starved_count": 0},
    })

    write_json(paths["data_health"], {
        "summary": {"sources": {"source-a": {"availability": 0.9, "field_completeness": 0.8, "coverage": 0.7, "consistency": 0.6}}}
    })

    report = AutonomousAudit(paths).collect()

    assert report["domains"]["runtime"]["state"] == "NOT_READY"
    assert report["data_health"]["sources"]["source-a"]["availability"] == 0.9
    assert report["fairness"]["starved_count"] == 1
    assert "backlog_increasing" in report["trend"]["anomalies"]
    assert report["recommended_action"]["code"] == "resolve_task_starvation"


def test_fairness_reports_unclaimed_service_debt_without_relabeling_starvation(tmp_path):
    paths = audit_paths(tmp_path)
    now = datetime.now()
    write_task(paths["task_pool"], task(
        "old-unclaimed",
        priority="medium",
        creator="file_scanner",
        created_at=(now - timedelta(hours=48)).isoformat(),
        last_claimed_at="",
    ))
    write_task(paths["task_pool"], task(
        "new-unclaimed",
        priority="high",
        creator="observation_to_task",
        created_at=(now - timedelta(hours=2)).isoformat(),
        last_claimed_at="",
    ))
    write_task(paths["task_pool"], task(
        "claimed-rework",
        priority="medium",
        creator="file_scanner",
        created_at=(now - timedelta(hours=72)).isoformat(),
        last_claimed_at=(now - timedelta(hours=1)).isoformat(),
    ))

    report = AutonomousAudit(paths, now=now).collect()

    assert report["fairness"]["starved_count"] == 0
    debt = report["fairness"]["unclaimed_service_debt"]
    assert debt["count"] == 2
    assert debt["claimed_pending_count"] == 1
    assert debt["age_hours"] == {"oldest": 48.0, "median": 25.0, "p95": 48.0}
    assert debt["by_source"] == {"file_scanner": 1, "observation_to_task": 1}
    assert debt["by_priority"] == {"high": 1, "medium": 1}
    assert [item["task_id"] for item in debt["oldest_tasks"]] == [
        "RQ-old-unclaimed",
        "RQ-new-unclaimed",
    ]


def test_fairness_splits_pending_rework_by_hard_objection_and_retry_readiness(tmp_path):
    paths = audit_paths(tmp_path)
    now = datetime.now()
    write_task(paths["task_pool"], task(
        "hard-rework",
        last_claimed_at=(now - timedelta(hours=2)).isoformat(),
        retry_after=(now - timedelta(minutes=1)).isoformat(),
        outputs={"last_validator_result": {
            "outcome": "rework_pending",
            "hard_objections": ["independent evidence is insufficient"],
            "advisory_objections": ["seek a counterexample"],
        }},
    ))
    write_task(paths["task_pool"], task(
        "qualified-rework",
        last_claimed_at=(now - timedelta(hours=1)).isoformat(),
        retry_after=(now - timedelta(minutes=1)).isoformat(),
        outputs={"last_validator_result": {
            "outcome": "rework_pending",
            "hard_objections": [],
            "advisory_objections": ["improve explanation"],
        }},
    ))
    write_task(paths["task_pool"], task(
        "cooldown-rework",
        last_claimed_at=now.isoformat(),
        retry_after=(now + timedelta(minutes=5)).isoformat(),
        outputs={"last_validator_result": {
            "outcome": "rework_pending",
            "hard_objections": [],
            "advisory_objections": [],
        }},
    ))

    debt = AutonomousAudit(paths, now=now).collect()["fairness"]["rework_service_debt"]

    assert debt["count"] == 3
    assert debt["hard_objection_count"] == 1
    assert debt["no_hard_objection_count"] == 2
    assert debt["retry_ready_count"] == 2
    assert debt["retry_not_due_count"] == 1
    assert debt["hard_objections"] == {"independent evidence is insufficient": 1}
    assert debt["representative_task_ids"] == {
        "hard_objection": ["RQ-hard-rework"],
        "no_hard_objection": ["RQ-cooldown-rework", "RQ-qualified-rework"],
    }


def test_run_writes_reports_and_preserves_runtime_sources(tmp_path):
    paths = audit_paths(tmp_path)
    write_json(paths["heartbeat"], {"status": "alive", "last_beat": datetime.now().isoformat(), "pid": 1})
    write_json(paths["daemon_state"], {"last_run": datetime.now().isoformat(), "cycle_progress": {"stage": "complete"}})
    write_json(paths["daemon_lock"], {"pid": 1})
    write_json(paths["heartbeat"].parent / "unrelated_runtime_state.json", {"unchanged": True})
    write_task(paths["task_pool"], task("pending"))
    for days in (91, 1):
        date = (datetime.now() - timedelta(days=days)).date().isoformat()
        write_json(paths["audits"] / "history" / date / "daily_health.json", {})

    before = source_hashes(paths)
    runtime_before = tree_hashes(paths["heartbeat"].parents[1], {paths["audits"]})
    result = run_audit(paths)

    assert result["written"] == {
        "daily_health.json",
        "daily_health.md",
        "blocking_reasons.json",
        "trend_report.json",
    }
    assert source_hashes(paths) == before
    assert tree_hashes(paths["heartbeat"].parents[1], {paths["audits"]}) == runtime_before
    for filename in result["written"]:
        assert (paths["audits"] / filename).is_file()
    old_date = (datetime.now() - timedelta(days=91)).date().isoformat()
    assert not (paths["audits"] / "history" / old_date).exists()
    assert (paths["audits"] / "history" / datetime.now().date().isoformat() / "daily_health.json").is_file()
