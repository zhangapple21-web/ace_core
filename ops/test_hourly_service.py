from core.hourly_service import HourlyTaskService


def test_hourly_service_records_existing_lifecycle_without_scheduler(tmp_path):
    report = HourlyTaskService(str(tmp_path)).record(10, {"researched": 2, "validated": 1, "archived": 1})
    assert report["service_status"] == "WORK_SERVICED"
    assert report["scheduler_created"] is False
    assert report["claim_and_research"] == 2
    # A local method call without executor identity is not evidence that the
    # sole daemon ran it.  The report must say so rather than self-certify.
    assert report["execution_evidence"]["status"] == "UNATTRIBUTED_LOCAL_CALL"
    assert report["execution_evidence"]["runtime_proof"] is False


def test_hourly_service_binds_a_matching_daemon_context_without_claiming_independent_proof(tmp_path):
    report = HourlyTaskService(str(tmp_path)).record(
        0,
        {"researched": 0, "validated": 0, "archived": 0},
        executor_context={"pid": 42, "run_id": "live-run", "lock_binding": "matched"},
    )
    assert report["execution_evidence"] == {
        "status": "DAEMON_CONTEXT_BOUND",
        "runtime_proof": False,
        "executor": {"pid": 42, "run_id": "live-run", "lock_binding": "matched"},
        "semantics": "daemon context is an attributable execution receipt, not independent runtime proof",
    }


