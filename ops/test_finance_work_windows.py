from datetime import datetime

from core.finance_work_windows import FinanceWorkWindows


def test_window_reports_research_only_when_data_is_degraded(tmp_path):
    evidence = tmp_path / "stock_data_evidence"
    evidence.mkdir()
    (evidence / "A_SHARE_DATA_CAPABILITY_MATRIX.json").write_text(
        '{"phase_two_admission":{"core_operations":{"daily_kline":{"production_sources":["a","b"],"has_independent_cross_validation":true}}}}',
        encoding="utf-8",
    )
    report = FinanceWorkWindows(str(tmp_path)).build(
        datetime(2026, 8, 25, 12, 45, tzinfo=FinanceWorkWindows(str(tmp_path)).timezone)
    )
    assert report["window"] == "midday_review"
    assert report["window_status"] == "RESEARCH_ONLY"
    assert report["task_created"] is False
    assert report["recommendation_allowed"] is False
    assert report["cognitive_workstreams"]


def test_window_not_due_is_auditable_without_side_effects(tmp_path):
    report = FinanceWorkWindows(str(tmp_path)).build(
        datetime(2026, 8, 25, 10, 30, tzinfo=FinanceWorkWindows(str(tmp_path)).timezone)
    )
    assert report["window"] is None
    assert report["window_status"] == "WINDOW_NOT_DUE"
    assert report["model_call"] is False
