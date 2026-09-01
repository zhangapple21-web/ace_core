from core.daily_shift import DailyShift
from core.free_zone_semantic_exploration import (
    SELECTION_POLICY_VERSION,
    SEMANTIC_SLICE_SCHEMA_VERSION,
)
from core.task import TaskPool
import json


def test_daily_shift_is_evidence_only(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task("completed", creator="test")
    task.audit_log.append({"event": "transition", "from": "pending", "to": "active", "reason": "lease_claimed", "at": "2026-08-25T09:00:00"})
    task.audit_log.append({"event": "transition", "from": "active", "to": "review", "actor": "researcher", "at": "2026-08-25T09:01:00"})
    task.audit_log.append({"event": "transition", "from": "review", "to": "approved", "actor": "validator", "at": "2026-08-25T09:02:00"})
    task.audit_log.append({"event": "transition", "from": "approved", "to": "archived", "at": "2026-08-25T09:03:00"})
    pool.update_task(task)
    report = DailyShift(pool, str(tmp_path / "data")).build("2026-08-25")
    assert report["no_synthetic_work"] is True
    assert report["taskpool"]["lifecycle_transitions"]["claim"] == 1
    assert report["taskpool"]["lifecycle_transitions"]["validation"] == 1
    assert report["taskpool"]["lifecycle_transitions"]["approved"] == 1
    assert len(pool.list_tasks()) == 1


def test_daily_shift_surfaces_shadow_model_performance(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "daily_growth_latest.json").write_text(
        '{"model_performance_ledger":{"shadow_only":true,"group_count":1}}',
        encoding="utf-8",
    )

    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data)).build(
        "2026-08-25"
    )

    assert report["model_performance"] == {
        "shadow_only": True,
        "group_count": 1,
    }
    assert "Model performance: `1` groups" in (data / "daily_shift_latest.md").read_text(
        encoding="utf-8"
    )


def test_daily_shift_reads_paper_evaluation_journal_without_creating_records(tmp_path):
    from core.paper_evaluation_journal import PaperEvaluationJournal
    data = tmp_path / "data"
    journal = PaperEvaluationJournal(str(data))
    journal.record({
        "evaluation_id": "EVAL-DAILY", "mode": "EVALUATION_ONLY", "publication_authority": False,
        "not_a_recommendation": True, "recorded_at": "2026-08-25T10:00:00+08:00",
        "observation_at": "2026-08-25T09:35:00+08:00", "symbol": "600000", "reference_price": 10.0,
        "hypothesis": "test", "invalidating_conditions": ["condition"], "data_snapshot_hash": "hash",
        "source_refs": ["a", "b"], "data_quality_state": "DEGRADED", "feature_version": "v1",
        "strategy_id": "strategy", "strategy_version": "v1",
        "horizon_policy": {"version": "v1", "horizons": [7], "calendar": "explicit_upstream"},
        "micro_observation": {
            "contract_version": "ace.micro_observation.v1", "observation": "quote snapshot",
            "intent": "test", "constraints": ["paper only"], "action": "record",
            "result": "recorded", "feedback": "await outcome", "next_question": "does it hold?",
            "evidence_refs": ["a"], "production_integration": False,
        },
    })
    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data)).build("2026-08-25")
    assert report["paper_evaluation_journal"]["recorded_count"] == 1
    assert report["finance_postmortem"]["status"] == "NO_ELIGIBLE_PRIOR_RECORD"


def test_daily_shift_distinguishes_current_taskpool_snapshot_from_daily_totals_and_lists_all_windows(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "daily_growth_latest.json").write_text(
        '{"archived_task_count":7,"attempted_production_model_call_count":2}',
        encoding="utf-8",
    )
    (data / "finance_work_windows_latest.json").write_text(json.dumps({
        "date": "2026-08-25",
        "window": "next_day_watchlist",
        "window_status": "RESEARCH_ONLY",
        "daily_windows": {
            "morning_observation": {"observed_at": "2026-08-25T09:01:00+08:00", "window_status": "RESEARCH_ONLY"},
            "midday_review": {"observed_at": "2026-08-25T12:33:00+08:00", "window_status": "RESEARCH_ONLY"},
        },
    }), encoding="utf-8")

    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data)).build("2026-08-25")

    assert report["taskpool"]["current_status_counts"] == {}
    assert report["completed_work"]["today_cumulative_archived_task_count"] == 7
    assert report["finance_window_coverage"]["observed_windows"] == [
        "morning_observation", "midday_review"
    ]
    assert report["finance_window_coverage"]["missing_windows"] == [
        "open_validation", "close_review", "next_day_watchlist"
    ]
    markdown = (data / "daily_shift_latest.md").read_text(encoding="utf-8")
    assert "TaskPool current snapshot" in markdown
    assert "Finance windows observed today" in markdown


def test_daily_shift_surfaces_external_learning_status(tmp_path):
    data = tmp_path / "data"
    result_dir = data / "memory" / "daily_learning" / "daily_results"
    result_dir.mkdir(parents=True)
    (result_dir / "2026-08-25.json").write_text(
        '{"mode":"none","outcome":"NO_VALID_LEARNING_TARGET",'
        '"external_learning":{"status":"SOURCE_UNAVAILABLE"}}',
        encoding="utf-8",
    )
    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data)).build("2026-08-25")
    assert report["daily_learning"]["external_learning"]["status"] == "SOURCE_UNAVAILABLE"
    assert "external `SOURCE_UNAVAILABLE`" in (data / "daily_shift_latest.md").read_text(encoding="utf-8")


def test_daily_shift_treats_local_archives_as_lifecycle_telemetry_not_value(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "daily_growth_latest.json").write_text(
        json.dumps({
            "outcome": "NO_MEASURABLE_GROWTH",
            "archived_task_count": 3,
            "archived_model_task_count": 0,
            "attempted_production_model_call_count": 0,
        }),
        encoding="utf-8",
    )

    report = DailyShift(
        TaskPool(str(tmp_path / "task_pool")), str(data)
    ).build("2026-08-25")

    completed = report["completed_work"]
    assert completed["experience_deposition"] is False
    assert completed["archived_task_count"] == 3
    assert completed["archived_model_task_count"] == 0
    markdown = (data / "daily_shift_latest.md").read_text(encoding="utf-8")
    assert "Execution and outcomes" in markdown
    assert "Completed today" not in markdown


def test_daily_shift_distinguishes_a_recorded_learning_snapshot_from_current_task_lifecycle(tmp_path):
    data = tmp_path / "data"
    result_dir = data / "memory" / "daily_learning" / "daily_results"
    result_dir.mkdir(parents=True)
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task("Learning result", creator="test")
    claimed = pool.claim_task(task.task_id, "test-worker")
    assert claimed is not None
    review = pool.move_task(
        task.task_id,
        "review",
        actor="test",
        reason="completed",
        task=claimed,
        claim_id=claimed.claim_id,
    )
    assert review is not None
    approved = pool.move_task(task.task_id, "approved", actor="test", reason="validated", task=review)
    assert approved is not None
    archived = pool.move_task(task.task_id, "archived", actor="test", reason="retained", task=approved)
    assert archived is not None
    (result_dir / "2026-08-27.json").write_text(json.dumps({
        "mode": "internal",
        "outcome": "queued_research",
        "reason": "requires_independent_miner_review",
        "candidate": "bounded archaeology",
        "task_id": task.task_id,
        "lifecycle_stage": "Research",
    }), encoding="utf-8")

    report = DailyShift(pool, str(data)).build("2026-08-27")

    assert report["daily_learning"]["outcome"] == "queued_research"
    assert report["daily_learning"]["task_runtime"]["task_id"] == task.task_id
    assert report["daily_learning"]["task_runtime"]["status"] == "archived"
    assert report["daily_learning"]["task_runtime"]["recorded_snapshot_outcome"] == "queued_research"
    assert f"task `{task.task_id}` currently `archived`" in (data / "daily_shift_latest.md").read_text(encoding="utf-8")


def test_daily_shift_ignores_neighboring_free_zone_reports(tmp_path):
    data = tmp_path / "data"
    sandbox = tmp_path / "sandbox"
    reports = sandbox / "reports"
    reports.mkdir(parents=True)
    (reports / "sandbox_society_latest.json").write_text(json.dumps({
        "at": "2026-08-25T15:00:00Z",
        "roles": {
            "free_zone": {"clean_experiment_count": 2, "quarantine_count": 1},
            "curator": {"new_proposal_ids": ["EXP-ONE"], "new_distillations": [{"experiment_id": "EXP-FAIL", "status": "COUNTEREXAMPLE_ONLY"}]},
            "court": {"status": "VALID"},
            "lazy_cat": {
                "fit_for_teacher_review_count": 1,
                "return_to_free_zone_count": 1,
                "total_verdict_count": 2,
                "new_challenge_ids": ["CHALLENGE-EXP-FAIL"],
                "pending_challenge_count": 1,
            },
            "teacher": {"review_queue": [{"experiment_id": "EXP-ONE"}], "counterexample_queue": [{"experiment_id": "EXP-FAIL"}]},
        },
        "design_seed": {"status": "DESIGN_SEED_OBSERVED", "route": ["observe", "review"]},
        "factories": {
            "recovery_thread_count": 2,
            "mark_count": 2,
            "world_count": 4,
            "processing_receipt_count": 1,
            "courier_receipt_count": 0,
            "smelter_receipt_count": 1,
        },
    }), encoding="utf-8")
    (reports / "museum_archaeology_latest.json").write_text(json.dumps({
        "event": "NO_NEW_MUSEUM_WORK",
        "museum_role": "INBOUND_FOOD_ONLY",
        "court_status": "DEFERRED_TO_OUTBOUND_DISTILLATION",
    }), encoding="utf-8")
    (reports / "free_zone_autonomy_latest.json").write_text(json.dumps({
        "event": "FREE_ZONE_EXPERIMENT_EXECUTED",
        "judgment": {"selected_fingerprint": "distillation:COUNTEREXAMPLE_ONLY:EXP-FAIL"},
        "claims": [{"source_kind": "distillation"}],
        "executions": [{"outcome": "PASS"}],
        "resource_selection": {
            "selection_policy_version": SELECTION_POLICY_VERSION,
            "semantic_slice_schema_version": SEMANTIC_SLICE_SCHEMA_VERSION,
            "selection_seed": 73,
            "candidate_snapshot_sha256": "snapshot",
            "semantic_slice_count": 2,
            "selected_count": 1,
            "quality_decision_performed": False,
            "outcome_used": False,
            "production_value_used": False,
        },
        "automatic_external_fetch": False,
    }), encoding="utf-8")

    report = DailyShift(
        TaskPool(str(tmp_path / "task_pool")),
        str(data),
    ).build("2026-08-25")

    assert "sandbox" not in report
    markdown = (data / "daily_shift_latest.md").read_text(encoding="utf-8")
    assert "Free zone:" not in markdown
    assert "Semantic exploration:" not in markdown
    assert "Lazy Cat:" not in markdown
    assert "Five factories:" not in markdown


def test_production_daily_shift_does_not_consume_or_surface_free_zone(tmp_path):
    """The Free Zone is a separate world, not an ACE production report slot."""
    data = tmp_path / "data"

    report = DailyShift(
        TaskPool(str(tmp_path / "task_pool")),
        str(data),
    ).build("2026-08-29")

    assert "sandbox" not in report
    markdown = (data / "daily_shift_latest.md").read_text(encoding="utf-8")
    assert "Free zone:" not in markdown
    assert "Semantic exploration:" not in markdown
    assert "Lazy Cat:" not in markdown
    assert "Five factories:" not in markdown
