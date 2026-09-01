import json

from core.continuity_audit import ContinuityAuditor


def _root(tmp_path):
    (tmp_path / "00_ROOT").mkdir()
    (tmp_path / "core").mkdir()
    (tmp_path / "06_RUNTIME" / "ace" / "data" / "memory").mkdir(parents=True)
    (tmp_path / "task_pool").mkdir()
    (tmp_path / "07_SANDBOX" / "free_research").mkdir(parents=True)
    (tmp_path / "AGENTS.md").write_text("continuity first\n", encoding="utf-8")
    (tmp_path / "ace_config.json").write_text('{"version":"1"}\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("ACE\n", encoding="utf-8")
    (tmp_path / "00_ROOT" / "PRINCIPLES.md").write_text("do not fabricate\n", encoding="utf-8")
    (tmp_path / "00_ROOT" / "ARCHITECTURE.md").write_text("motherplate\n", encoding="utf-8")
    (tmp_path / "ace_daemon.py").write_text("runtime\n", encoding="utf-8")
    (tmp_path / "core" / "task.py").write_text("taskpool\n", encoding="utf-8")
    (tmp_path / "core" / "daily_shift.py").write_text("daily shift\n", encoding="utf-8")
    (tmp_path / "core" / "free_research_sandbox.py").write_text("sandbox\n", encoding="utf-8")
    (tmp_path / "core" / "free_zone_reality_bridge.py").write_text("bridge\n", encoding="utf-8")
    (tmp_path / "core" / "free_zone_model_research.py").write_text("model research\n", encoding="utf-8")
    (tmp_path / "core" / "free_zone_model_shift.py").write_text("model shift\n", encoding="utf-8")
    (tmp_path / "core" / "meaning_line.py").write_text("explicit meaning contract\n", encoding="utf-8")
    (tmp_path / "core" / "stock_data_reliability.py").write_text("stock data\n", encoding="utf-8")
    (tmp_path / "core" / "data_admission_recovery.py").write_text("recovery\n", encoding="utf-8")
    (tmp_path / "core" / "continuity_audit.py").write_text("continuity audit\n", encoding="utf-8")
    (tmp_path / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json").write_text(
        json.dumps({"pid": 7, "run_id": "run-a", "cycle_progress": {"cycle_status": "completed"}}),
        encoding="utf-8",
    )
    (tmp_path / "06_RUNTIME" / "ace" / "data" / "memory" / "heartbeat.json").write_text(
        json.dumps({"pid": 7, "run_id": "run-a", "status": "alive"}), encoding="utf-8"
    )
    return tmp_path


def test_first_continuity_record_is_established_not_proven(tmp_path):
    report = ContinuityAuditor(_root(tmp_path)).audit(record=True, host_id="host-a")

    assert report["continuity_status"] == "CONTINUITY_ESTABLISHED"
    assert report["claim_level"] == "BASELINE_ONLY"
    assert report["side_effects"] == {"taskpool_mutated": False, "model_called": False, "production_changed": False}


def test_restart_with_untampered_ledger_verifies_continuity(tmp_path):
    root = _root(tmp_path)
    auditor = ContinuityAuditor(root)
    auditor.audit(record=True, host_id="host-a")
    report = auditor.audit(record=True, host_id="host-a")

    assert report["continuity_status"] == "CONTINUITY_VERIFIED"
    assert report["claim_level"] == "HASH_CHAIN_AND_ANCHORS"
    assert report["ledger"]["chain_valid"] is True


def test_missing_startup_anchor_snapshot_never_claims_daemon_adoption(tmp_path):
    report = ContinuityAuditor(_root(tmp_path)).audit(record=False, host_id="host-a")

    adoption = report["runtime_footprint"]["runtime_adoption"]
    assert adoption["status"] == "DAEMON_LOADED_VERSION_UNATTESTED"
    assert adoption["loaded_anchor_set_sha256"] is None


def test_anchor_snapshot_only_proves_current_code_after_a_matching_startup(tmp_path):
    root = _root(tmp_path)
    auditor = ContinuityAuditor(root)
    snapshot = auditor.current_anchor_snapshot()
    state_path = root / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["loaded_anchor_set_sha256"] = snapshot["anchor_set_sha256"]
    state_path.write_text(json.dumps(state), encoding="utf-8")

    matched = auditor.audit(record=False, host_id="host-a")
    assert matched["runtime_footprint"]["runtime_adoption"]["status"] == "DAEMON_LOADED_CURRENT_ANCHORS"

    (root / "core" / "meaning_line.py").write_text("changed after startup\n", encoding="utf-8")
    stale = auditor.audit(record=False, host_id="host-a")
    assert stale["runtime_footprint"]["runtime_adoption"]["status"] == "DAEMON_RESTART_REQUIRED_FOR_CURRENT_ANCHORS"


def test_host_change_is_a_migration_not_a_new_identity_when_chain_is_valid(tmp_path):
    root = _root(tmp_path)
    auditor = ContinuityAuditor(root)
    auditor.audit(record=True, host_id="host-a")
    report = auditor.audit(record=True, host_id="host-b")

    assert report["continuity_status"] == "CONTINUITY_VERIFIED_AFTER_MIGRATION"
    assert report["migration"]["detected"] is True
    assert report["migration"]["previous_host_id"] == "host-a"


def test_changed_motherplate_anchor_is_disclosed_before_continuity_is_reverified(tmp_path):
    root = _root(tmp_path)
    auditor = ContinuityAuditor(root)
    auditor.audit(record=True, host_id="host-a")
    (root / "AGENTS.md").write_text("continuity first, revised\n", encoding="utf-8")

    changed = auditor.audit(record=True, host_id="host-a")
    verified = auditor.audit(record=False, host_id="host-a")

    assert changed["continuity_status"] == "CONTINUITY_CHANGED_UNATTESTED"
    assert "ANCHOR_SET_CHANGED" in changed["reason_codes"]
    assert changed["anchor_changes_since_previous_receipt"]["modified"] == ["AGENTS.md"]
    assert verified["continuity_status"] == "CONTINUITY_VERIFIED"


def test_tampered_history_fails_closed_instead_of_claiming_continuity(tmp_path):
    root = _root(tmp_path)
    auditor = ContinuityAuditor(root)
    auditor.audit(record=True, host_id="host-a")
    ledger = root / "06_RUNTIME" / "ace" / "data" / "memory" / "continuity" / "ledger.jsonl"
    entry = json.loads(ledger.read_text(encoding="utf-8").strip())
    entry["anchors"]["AGENTS.md"] = "forged"
    ledger.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    report = auditor.audit(record=False, host_id="host-a")

    assert report["continuity_status"] == "CONTINUITY_DEGRADED"
    assert "LEDGER_HASH_INVALID" in report["reason_codes"]


def test_missing_motherplate_anchor_fails_closed(tmp_path):
    root = _root(tmp_path)
    (root / "00_ROOT" / "PRINCIPLES.md").unlink()

    report = ContinuityAuditor(root).audit(record=False, host_id="host-a")

    assert report["continuity_status"] == "CONTINUITY_DEGRADED"
    assert "MISSING_REQUIRED_ANCHOR:00_ROOT/PRINCIPLES.md" in report["reason_codes"]


def test_daemon_lifecycle_helper_records_a_receipt_without_runtime_side_effects(tmp_path):
    from ace_daemon import AceDaemon

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.continuity_auditor = ContinuityAuditor(_root(tmp_path))
    daemon.run_id = "run-a"
    daemon.daemon_lock_token = "sole-lock"
    daemon._log_error = lambda *_args, **_kwargs: None

    report = daemon._record_continuity("daemon_startup")

    assert report["runtime_context"]["event"] == "daemon_startup"
    assert report["runtime_context"]["sole_daemon_lock_held"] is True
    assert report["side_effects"]["taskpool_mutated"] is False


def test_startup_archives_prior_exit_without_presenting_it_as_current_state():
    from ace_daemon import AceDaemon

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.state = {
        "run_id": "old-run",
        "last_exit_reason": "fatal_error: historical sharing violation",
        "last_exit_time": "2026-08-31T01:00:00+00:00",
    }
    daemon.run_id = "new-run"
    daemon._save_state = lambda: None

    daemon._checkpoint_startup()

    assert daemon.state["run_status"] == "alive"
    assert daemon.state["previous_run_exit"]["run_id"] == "old-run"
    assert daemon.state["previous_run_exit"]["reason"].startswith("fatal_error:")


def test_startup_captures_the_anchor_snapshot_that_the_new_run_loaded():
    from ace_daemon import AceDaemon

    class Auditor:
        def current_anchor_snapshot(self):
            return {"anchor_set_sha256": "anchor-hash", "anchor_count": 1, "reason_codes": []}

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.state = {}
    daemon.run_id = "new-run"
    daemon.continuity_auditor = Auditor()
    daemon._save_state = lambda: None

    daemon._checkpoint_startup()

    assert daemon.state["loaded_anchor_set_sha256"] == "anchor-hash"
    assert daemon.state["loaded_anchor_snapshot_reasons"] == []


def test_daily_shift_exposes_a_continuity_receipt_without_turning_it_into_runtime_proof(tmp_path):
    from core.daily_shift import DailyShift
    from core.task import TaskPool

    data_dir = _root(tmp_path) / "06_RUNTIME" / "ace" / "data" / "memory"
    ContinuityAuditor(tmp_path).audit(record=True, host_id="host-a")

    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data_dir)).build("2026-08-31")

    assert report["continuity_audit"]["continuity_status"] == "CONTINUITY_ESTABLISHED"
    assert "natural cycle" not in report["continuity_audit"].get("claim_level", "").lower()
    assert report["free_zone_model_shift"]["runtime_adoption_status"] == "DAEMON_NOT_YET_OBSERVED"
