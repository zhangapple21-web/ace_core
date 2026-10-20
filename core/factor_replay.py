"""Leakage-aware factor replay and walk-forward validation.

Inputs are already normalized point-in-time rows.  This module never fetches
data and never turns a backtest result into a recommendation.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Callable, Mapping, Sequence

STATUS_COMPLETE = "COMPLETE"
STATUS_INCOMPLETE = "INCOMPLETE"
STATUS_LOW_SAMPLE = "LOW_SAMPLE"

REASON_LEAKAGE = "feature_not_before_outcome"
REASON_UNPARSEABLE_TIME = "time_unparseable"
REASON_MISSING_NUMBER = "score_or_outcome_missing"
REASON_MISSING_TIME = "feature_or_outcome_time_missing"


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _time_error(feature: str, outcome: str, time_format: str | None) -> str | None:
    if not feature or not outcome:
        return REASON_MISSING_TIME
    if time_format is None:
        # Preserve the legacy comparison for fixed-width ISO date/time strings.
        return REASON_LEAKAGE if feature >= outcome else None
    try:
        feature_at = datetime.strptime(feature, time_format)
        outcome_at = datetime.strptime(outcome, time_format)
    except ValueError:
        return REASON_UNPARSEABLE_TIME
    return REASON_LEAKAGE if feature_at >= outcome_at else None


def replay_factor(
    rows: Sequence[Mapping[str, Any]],
    factor: Callable[[Mapping[str, Any]], Any],
    *,
    feature_time_key: str = "feature_time",
    outcome_time_key: str = "outcome_time",
    outcome_key: str = "forward_return",
    time_format: str | None = None,
) -> dict[str, Any]:
    """Replay a factor while rejecting rows whose feature is after its outcome."""

    accepted: list[dict[str, float]] = []
    rejected = 0
    rejection_reasons: dict[str, int] = {}

    def reject(reason: str) -> None:
        nonlocal rejected
        rejected += 1
        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

    for row in rows:
        feature_time = str(row.get(feature_time_key, ""))
        outcome_time = str(row.get(outcome_time_key, ""))
        time_error = _time_error(feature_time, outcome_time, time_format)
        if time_error is not None:
            reject(time_error)
            continue
        score = _number(factor(row))
        outcome = _number(row.get(outcome_key))
        if score is None or outcome is None:
            reject(REASON_MISSING_NUMBER)
            continue
        accepted.append({"score": score, "outcome": outcome})

    if not accepted:
        return {
            "status": STATUS_INCOMPLETE,
            "accepted": 0,
            "rejected": rejected,
            "mean_return": None,
            "hit_rate": None,
            "rejection_reasons": rejection_reasons,
        }
    mean_return = sum(item["outcome"] for item in accepted) / len(accepted)
    hit_rate = sum(item["outcome"] > 0 for item in accepted) / len(accepted)
    return {
        "status": STATUS_COMPLETE,
        "accepted": len(accepted),
        "rejected": rejected,
        "mean_return": round(mean_return, 8),
        "hit_rate": round(hit_rate, 6),
        "rejection_reasons": rejection_reasons,
    }


def walk_forward_validate(
    rows: Sequence[Mapping[str, Any]],
    factor: Callable[[Mapping[str, Any]], Any],
    *,
    train_size: int,
    test_size: int,
    feature_time_key: str = "feature_time",
    outcome_time_key: str = "outcome_time",
    outcome_key: str = "forward_return",
    time_format: str | None = None,
) -> dict[str, Any]:
    """Run rolling out-of-sample windows; test rows never enter training stats."""

    if train_size < 1 or test_size < 1:
        raise ValueError("window_sizes_must_be_positive")
    ordered = list(rows)
    windows: list[dict[str, Any]] = []
    replay_options = {
        "feature_time_key": feature_time_key,
        "outcome_time_key": outcome_time_key,
        "outcome_key": outcome_key,
        "time_format": time_format,
    }
    start = 0
    while start + train_size + test_size <= len(ordered):
        train = ordered[start : start + train_size]
        test = ordered[start + train_size : start + train_size + test_size]
        train_result = replay_factor(train, factor, **replay_options)
        test_result = replay_factor(test, factor, **replay_options)
        windows.append({"train": train_result, "test": test_result})
        start += test_size
    if not windows:
        return {
            "status": STATUS_LOW_SAMPLE,
            "windows": [],
            "oos_mean_return": None,
            "oos_windows": 0,
            "production_eligible": False,
            "reason": "no_complete_window",
        }
    oos = [w["test"]["mean_return"] for w in windows if w["test"]["mean_return"] is not None]
    return {
        "status": STATUS_COMPLETE if len(oos) >= 2 else STATUS_LOW_SAMPLE,
        "windows": windows,
        "oos_mean_return": round(sum(oos) / len(oos), 8) if oos else None,
        "oos_windows": len(oos),
        "production_eligible": False,
        "reason": "research_only_until_live_sample_validation",
    }
