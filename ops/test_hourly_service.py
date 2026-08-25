from core.hourly_service import HourlyTaskService


def test_hourly_service_records_existing_lifecycle_without_scheduler(tmp_path):
    report = HourlyTaskService(str(tmp_path)).record(10, {"researched": 2, "validated": 1, "archived": 1})
    assert report["service_status"] == "WORK_SERVICED"
    assert report["scheduler_created"] is False
    assert report["claim_and_research"] == 2
