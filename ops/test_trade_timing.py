from datetime import timedelta

import pytest

from core.trade_timing import assess_trade_window


BASE = "2026-09-08T09:35:00+08:00"


def test_near_limit_move_is_not_written_as_an_entry():
    result = assess_trade_window(
        observed_at=BASE,
        as_of="2026-09-08T09:36:00+08:00",
        change_pct=9.2,
    )
    assert result["status"] == "LATE_HIGH_MOVE"
    assert result["message_window"] == "WAIT_FOR_PULLBACK_OR_NEXT_SETUP"


def test_limit_up_is_a_missed_window():
    result = assess_trade_window(
        observed_at=BASE,
        as_of="2026-09-08T09:36:00+08:00",
        change_pct=10.0,
        is_limit_up=True,
    )
    assert result["status"] == "WINDOW_MISSED"


def test_four_to_five_percent_move_needs_confirmation():
    result = assess_trade_window(
        observed_at=BASE,
        as_of="2026-09-08T09:36:00+08:00",
        change_pct=4.8,
        confirmation_available=False,
    )
    assert result["status"] == "WAIT_FOR_CONFIRMATION"
    assert result["score_contribution"] == 0.0


def test_stale_snapshot_is_blocked_before_client_message():
    result = assess_trade_window(
        observed_at=BASE,
        as_of="2026-09-08T09:46:00+08:00",
        change_pct=3.0,
    )
    assert result["status"] == "STALE_SNAPSHOT"


def test_timestamps_need_timezone_and_order():
    with pytest.raises(ValueError, match="must_include_timezone"):
        assess_trade_window(observed_at="2026-09-08T09:35:00", as_of="2026-09-08T09:36:00+08:00", change_pct=3)
    with pytest.raises(ValueError, match="before"):
        assess_trade_window(observed_at="2026-09-08T09:36:00+08:00", as_of=BASE, change_pct=3)
