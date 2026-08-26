import tempfile
import json
from pathlib import Path

from core.daily_growth import DailyGrowthLedger
from core.task import TaskPool


def test_daily_growth_counts_archives_and_production_but_not_health_probes():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool = TaskPool(str(root / "task_pool"))
        task = pool.create_task("Model growth", creator="test", priority="high")
        task.outputs["model_task_admission"] = {
            "eligible": True,
            "classification": "reasoning",
        }
        task.outputs["model_execution"] = [{
            "task_type": "reasoning",
            "provider": "nim",
            "selected_model": "model-a",
            "api_called": True,
            "api_result": "success",
            "response_sha256": "abc",
            "at": "2026-08-25T10:00:00",
        }]
        task.audit_log.append({
            "event": "transition",
            "from": "approved",
            "to": "archived",
            "at": "2026-08-25T10:01:00",
        })
        pool.update_task(task)
        probe = pool.create_task("Health probe", creator="test")
        probe.outputs["model_execution"] = [{
            "task_type": "strategic",
            "provider": "shenwen",
            "selected_model": "gpt-5.6-sol",
            "api_called": True,
            "api_result": "success",
            "response_sha256": "probe",
            "at": "2026-08-25T10:00:30",
        }]
        pool.update_task(probe)

        report = DailyGrowthLedger(
            pool, str(root / "daily_growth.json")
        ).build("2026-08-25")
        assert report["outcome"] == "MEASURABLE_GROWTH"
        assert report["archived_task_count"] == 1
        assert report["archived_model_task_count"] == 1
        assert report["production_model_call_count"] == 1
        assert report["attempted_production_model_call_count"] == 1
        assert report["successful_production_model_call_count"] == 1
        assert report["production_model_call_semantics"]["scope"] == "calendar_day_admitted_model_execution_traces"
        assert report["health_probes_excluded"] is True


def test_daily_growth_separates_attempted_and_successful_production_calls():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool = TaskPool(str(root / "task_pool"))
        task = pool.create_task("Failed model execution", creator="test")
        task.outputs["model_task_admission"] = {
            "eligible": True,
            "classification": "reasoning",
        }
        task.outputs["model_execution"] = [
            {
                "api_called": True,
                "api_result": "success",
                "at": "2026-08-25T23:59:00",
            },
            {
                "api_called": True,
                "api_result": "failed",
                "at": "2026-08-26T09:00:00",
            },
        ]
        pool.update_task(task)

        report = DailyGrowthLedger(pool, str(root / "daily_growth.json")).build("2026-08-26")

        assert report["attempted_production_model_call_count"] == 1
        assert report["successful_production_model_call_count"] == 0
        assert report["production_model_call_count"] == 0  # legacy successful alias
        assert report["model_performance_ledger"]["production_call_count"] == 1


def test_daily_growth_builds_shadow_model_performance_from_production_traces():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool = TaskPool(str(root / "task_pool"))
        task = pool.create_task("Model performance", creator="test")
        task.outputs["model_task_admission"] = {
            "eligible": True,
            "classification": "reasoning",
        }
        task.outputs["model_execution"] = [
            {
                "task_type": "reasoning",
                "provider": "nim",
                "selected_model": "model-a",
                "api_called": True,
                "api_result": "success",
                "result": "success",
                "fallback": True,
                "latency_ms": 10,
                "cost": {"currency": "USD", "total_usd": 0.25},
                "at": "2026-08-25T10:00:00",
            },
            {
                "task_type": "reasoning",
                "provider": "nim",
                "selected_model": "model-a",
                "api_called": True,
                "api_result": "failed",
                "result": "failed",
                "fallback": False,
                "latency_ms": 30,
                "cost": {},
                "at": "2026-08-25T10:01:00",
            },
        ]
        task.outputs["last_validator_result"] = {"outcome": "approved"}
        pool.update_task(task)

        report = DailyGrowthLedger(
            pool, str(root / "daily_growth.json")
        ).build("2026-08-25")

        ledger = report["model_performance_ledger"]
        assert ledger["shadow_only"] is True
        assert ledger["routing_effect"] is False
        assert ledger["production_call_count"] == 2
        assert ledger["group_count"] == 1
        group = ledger["groups"][0]
        assert group["task_type"] == "reasoning"
        assert group["provider"] == "nim"
        assert group["model"] == "model-a"
        assert group["sample_count"] == 2
        assert group["success_rate"] == 0.5
        assert group["fallback_rate"] == 0.5
        assert group["latency_ms"] == {"count": 2, "average": 20.0, "p95": 30.0}
        assert group["cost"] == {
            "currency": "USD",
            "known_call_count": 1,
            "unknown_call_count": 1,
            "total": 0.25,
        }
        assert group["validator"] == {
            "task_count": 1,
            "assessed_task_count": 1,
            "accepted_task_count": 1,
            "accept_rate": 1.0,
        }


def test_daily_growth_records_degraded_finance_without_creating_work(tmp_path):
    data = tmp_path / "data"
    evidence = data / "stock_data_evidence"
    evidence.mkdir(parents=True)
    (evidence / "A_SHARE_DATA_CAPABILITY_MATRIX.json").write_text(json.dumps({
        "phase_two_admission": {"status": "NOT_ADMITTED", "core_operations": {
            "daily_kline": {"production_sources": ["a", "b"], "has_independent_cross_validation": True},
            "minute_kline_5m": {"production_sources": ["a", "b"], "has_independent_cross_validation": True},
            "quote": {"production_sources": []},
            "minute_kline_1m": {"production_sources": []},
            "index": {"production_sources": []},
        }}
    }), encoding="utf-8")
    pool = TaskPool(str(data / "task_pool"))

    report = DailyGrowthLedger(pool, str(data / "daily_growth_latest.json")).build("2026-08-25")

    assert report["finance_status"] == "DEGRADED"
    assert report["cognitive_work_supply"]["financial_research_work"] == 0


def test_daily_growth_allows_a_zero_growth_day():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        report = DailyGrowthLedger(
            TaskPool(str(root / "task_pool")),
            str(root / "daily_growth.json"),
        ).build("2026-08-25")
        assert report["outcome"] == "NO_MEASURABLE_GROWTH"
        assert report["no_growth_quota"] is True


def test_daily_growth_reports_cognitive_work_supply_from_existing_evidence():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data"
        observations = data / "observations"
        observations.mkdir(parents=True)
        (observations / "observations.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "obs_id": "OBS-1",
                    "source": "daemon_loop",
                    "created_at": "2026-08-25T08:00:00",
                }),
                json.dumps({
                    "obs_id": "OBS-2",
                    "source": "discovery_mode",
                    "created_at": "2026-08-25T08:05:00",
                }),
            ]),
            encoding="utf-8",
        )
        (data / "model_work_discovery_latest.json").write_text(
            json.dumps({
                "discovery_date": "2026-08-25",
                "outcome": "MODEL_WORK_CANDIDATE_OBSERVED",
                "admission_funnel": {
                    "candidate_count": 2,
                    "eligible_count": 1,
                    "rejected_count": 1,
                },
            }),
            encoding="utf-8",
        )
        pool = TaskPool(str(root / "task_pool"))
        local = pool.create_task("Local work", creator="test")
        local.created_at = "2026-08-25T08:10:00"
        pool.update_task(local)
        model = pool.create_task("Reasoning work", creator="test")
        model.created_at = "2026-08-25T08:06:00"
        model.tags = ["task_type:reasoning"]
        model.outputs["model_task_admission"] = {
            "eligible": True,
            "classification": "reasoning",
        }
        model.outputs["model_execution"] = [{
            "task_type": "reasoning",
            "provider": "nim",
            "selected_model": "model-a",
            "api_called": True,
            "api_result": "success",
            "response_sha256": "abc",
            "at": "2026-08-25T08:08:00",
        }]
        model.audit_log.append({
            "event": "transition",
            "from": "pending",
            "to": "active",
            "reason": "lease_claimed",
            "at": "2026-08-25T08:07:00",
        })
        pool.update_task(model)

        report = DailyGrowthLedger(
            pool, str(data / "daily_growth_latest.json")
        ).build("2026-08-25")
        supply = report["cognitive_work_supply"]
        assert supply["observations"] == 2
        assert supply["candidate_work"] == 2
        assert supply["accepted_work"] == 2
        assert supply["accepted_model_work"] == 1
        assert supply["admitted_candidate_work"] == 1
        assert supply["local_work"] == 1
        assert supply["reasoning_work"] == 1
        assert supply["strategic_work"] == 0
        assert supply["execution_work"] == 0
        assert supply["rejected_work"] == 1
        assert supply["deferred_work"] == 0
        assert supply["eligible_but_unserved"] == 0
        assert supply["model_calls"] == 1
        assert supply["discovery_yield"] == 1.0
        assert supply["admission_rejection_rate"] == 0.5
        assert supply["model_work_service_rate"] == 1.0
        assert supply["service_latency_seconds"]["median"] == 60.0
        assert supply["window_status"] == "MODEL_WORK_SERVICED"
        assert supply["coverage"]["complete"] is False
        assert supply["coverage"]["candidate_work"] == "model_work_discovery_only"


def test_three_daily_observation_windows_without_candidates_trigger_diagnosis():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data"
        observations = data / "observations"
        observations.mkdir(parents=True)
        observation_path = observations / "observations.jsonl"
        discovery_path = data / "model_work_discovery_latest.json"
        ledger = DailyGrowthLedger(
            TaskPool(str(root / "task_pool")),
            str(data / "daily_growth_latest.json"),
        )

        for offset, day in enumerate(("2026-08-23", "2026-08-24", "2026-08-25"), 1):
            with observation_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({
                    "obs_id": f"OBS-{offset}",
                    "source": "daemon_loop",
                    "created_at": f"{day}T08:00:00",
                }) + "\n")
            discovery_path.write_text(json.dumps({
                "discovery_date": day,
                "outcome": "NO_VALID_MODEL_WORK",
                "admission_funnel": {
                    "candidate_count": 0,
                    "eligible_count": 0,
                    "rejected_count": 0,
                },
            }), encoding="utf-8")
            report = ledger.build(day)

        supply = report["cognitive_work_supply"]
        assert supply["window_status"] == "NO_CANDIDATE_DISCOVERED"
        assert supply["consecutive_no_candidate_windows"] == 3
        assert supply["discovery_health"] == "INVESTIGATE_DISCOVERY_CHAIN"
        assert len(report["cognitive_work_supply_history"]) == 3

        same_day = ledger.build("2026-08-25")
        assert len(same_day["cognitive_work_supply_history"]) == 3
        assert (
            same_day["cognitive_work_supply"]["consecutive_no_candidate_windows"]
            == 3
        )


def test_rejected_candidate_has_distinct_no_model_call_reason():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data"
        observations = data / "observations"
        observations.mkdir(parents=True)
        (observations / "observations.jsonl").write_text(
            json.dumps({
                "obs_id": "OBS-1",
                "source": "discovery_mode",
                "created_at": "2026-08-25T08:00:00",
            }) + "\n",
            encoding="utf-8",
        )
        (data / "model_work_discovery_latest.json").write_text(json.dumps({
            "discovery_date": "2026-08-25",
            "outcome": "MODEL_WORK_CANDIDATE_OBSERVED",
            "admission_funnel": {
                "candidate_count": 1,
                "eligible_count": 0,
                "rejected_count": 1,
            },
        }), encoding="utf-8")

        report = DailyGrowthLedger(
            TaskPool(str(root / "task_pool")),
            str(data / "daily_growth_latest.json"),
        ).build("2026-08-25")
        supply = report["cognitive_work_supply"]
        assert supply["window_status"] == "CANDIDATE_FOUND_BUT_REJECTED"
        assert supply["model_calls"] == 0


def test_eligible_pending_model_work_is_reported_as_unserved():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = root / "data"
        observations = data / "observations"
        observations.mkdir(parents=True)
        (observations / "observations.jsonl").write_text(json.dumps({
            "obs_id": "OBS-1",
            "source": "discovery_mode",
            "created_at": "2026-08-25T08:00:00",
        }) + "\n", encoding="utf-8")
        (data / "model_work_discovery_latest.json").write_text(json.dumps({
            "discovery_date": "2026-08-25",
            "outcome": "MODEL_WORK_CANDIDATE_OBSERVED",
            "admission_funnel": {
                "candidate_count": 1,
                "eligible_count": 1,
                "rejected_count": 0,
            },
        }), encoding="utf-8")
        pool = TaskPool(str(root / "task_pool"))
        task = pool.create_task("Pending model work", creator="test")
        task.created_at = "2026-08-25T08:01:00"
        task.tags = ["task_type:reasoning"]
        task.outputs["model_task_admission"] = {
            "eligible": True,
            "classification": "reasoning",
        }
        pool.update_task(task)

        report = DailyGrowthLedger(
            pool, str(data / "daily_growth_latest.json")
        ).build("2026-08-25")
        supply = report["cognitive_work_supply"]
        assert supply["eligible_but_unserved"] == 1
        assert supply["model_work_service_rate"] == 0.0
        assert supply["window_status"] == "ELIGIBLE_WORK_NOT_SERVICED"
