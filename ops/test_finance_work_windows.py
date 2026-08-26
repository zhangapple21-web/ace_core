import json
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


def test_finance_status_requires_matrix_admission_before_full_ready(tmp_path):
    evidence = tmp_path / "stock_data_evidence"
    evidence.mkdir()
    required = {
        name: {
            "production_sources": ["source_a", "source_b"],
            "has_independent_cross_validation": True,
        }
        for name in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")
    }
    (evidence / "A_SHARE_DATA_CAPABILITY_MATRIX.json").write_text(
        json.dumps({"phase_two_admission": {"status": "NOT_ADMITTED", "core_operations": required}}),
        encoding="utf-8",
    )

    assert FinanceWorkWindows(str(tmp_path))._finance_status() == "DEGRADED"


def test_window_not_due_is_auditable_without_side_effects(tmp_path):
    report = FinanceWorkWindows(str(tmp_path)).build(
        datetime(2026, 8, 25, 10, 30, tzinfo=FinanceWorkWindows(str(tmp_path)).timezone)
    )
    assert report["window"] is None
    assert report["window_status"] == "WINDOW_NOT_DUE"
    assert report["model_call"] is False


def test_daily_window_history_is_preserved(tmp_path):
    windows = FinanceWorkWindows(str(tmp_path))
    windows.build(datetime(2026, 8, 25, 9, 5, tzinfo=windows.timezone))
    report = windows.build(datetime(2026, 8, 25, 15, 20, tzinfo=windows.timezone))
    assert set(report["daily_windows"]) == {"morning_observation", "close_review"}


def test_open_validation_refreshes_live_evidence_once_per_window(tmp_path):
    calls = []
    windows = FinanceWorkWindows(str(tmp_path))

    def refresh():
        calls.append(True)
        evidence = tmp_path / "stock_data_evidence"
        evidence.mkdir(exist_ok=True)
        (evidence / "A_SHARE_DATA_CAPABILITY_MATRIX.json").write_text(
            '{"phase_two_admission":{"core_operations":{}}}',
            encoding="utf-8",
        )
        return {"status": "completed", "completed_at": "2026-08-25T01:35:00+00:00"}

    windows.data_refresh = refresh
    now = datetime(2026, 8, 25, 9, 35, tzinfo=windows.timezone)
    first = windows.build(now)
    second = windows.build(now)

    assert len(calls) == 1
    assert first["data_refresh"]["status"] == "completed"
    assert second["data_refresh"]["status"] == "already_attempted_for_window"
    assert second["data_refresh"]["initial_result"] == first["data_refresh"]


def test_finance_windows_do_not_refresh_market_data_outside_open_validation(tmp_path):
    calls = []
    windows = FinanceWorkWindows(str(tmp_path))
    windows.data_refresh = lambda: calls.append(True)

    windows.build(datetime(2026, 8, 25, 9, 5, tzinfo=windows.timezone))
    windows.build(datetime(2026, 8, 25, 15, 20, tzinfo=windows.timezone))

    assert calls == []


def test_open_validation_does_not_refresh_on_configured_market_holiday(tmp_path):
    calls = []
    windows = FinanceWorkWindows(str(tmp_path))
    windows.data_refresh = lambda: calls.append(True)

    report = windows.build(datetime(2026, 10, 1, 9, 35, tzinfo=windows.timezone))

    assert calls == []
    assert report["window"] == "open_validation"
    assert report["data_refresh"] is None


def test_failed_open_refresh_is_audited_and_not_retried_every_cycle(tmp_path):
    calls = []
    windows = FinanceWorkWindows(str(tmp_path))

    def refresh():
        calls.append(True)
        raise RuntimeError("isolated refresh failure")

    windows.data_refresh = refresh
    now = datetime(2026, 8, 25, 9, 35, tzinfo=windows.timezone)
    first = windows.build(now)
    second = windows.build(now)

    assert first["data_refresh"] == {"status": "failed", "reason": "RuntimeError"}
    assert second["data_refresh"]["status"] == "already_attempted_for_window"
    assert len(calls) == 1
