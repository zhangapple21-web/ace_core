"""Leakage-aware factor replay and walk-forward validation.

Inputs are already normalized point-in-time rows.  This module never fetches
data and never turns a backtest result into a recommendation.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def replay_factor(
    rows: Sequence[Mapping[str, Any]],
    factor: Callable[[Mapping[str, Any]], Any],
    *,
    feature_time_key: str = "feature_time",
    outcome_time_key: str = "outcome_time",
    outcome_key: str = "forward_return",
) -> dict[str, Any]:
    """Replay a factor while rejecting rows whose feature is after its outcome."""

    accepted: list[dict[str, float]] = []
    rejected = 0
    for row in rows:
        feature_time = str(row.get(feature_time_key, ""))
        outcome_time = str(row.get(outcome_time_key, ""))
        if not feature_time or not outcome_time or feature_time >= outcome_time:
            rejected += 1
            continue
        score = _number(factor(row))
        outcome = _number(row.get(outcome_key))
        if score is None or outcome is None:
            rejected += 1
            continue
        accepted.append({"score": score, "outcome": outcome})

    if not accepted:
        return {"status": "INCOMPLETE", "accepted": 0, "rejected": rejected, "mean_return": None}
    mean_return = sum(item["outcome"] for item in accepted) / len(accepted)
    hit_rate = sum(item["outcome"] > 0 for item in accepted) / len(accepted)
    return {
        "status": "COMPLETE",
        "accepted": len(accepted),
        "rejected": rejected,
        "mean_return": round(mean_return, 8),
        "hit_rate": round(hit_rate, 6),
    }


def walk_forward_validate(
    rows: Sequence[Mapping[str, Any]],
    factor: Callable[[Mapping[str, Any]], Any],
    *,
    train_size: int,
    test_size: int,
) -> dict[str, Any]:
    """Run rolling out-of-sample windows; test rows never enter training stats."""

    if train_size < 1 or test_size < 1:
        raise ValueError("window_sizes_must_be_positive")
    ordered = list(rows)
    windows: list[dict[str, Any]] = []
    start = 0
    while start + train_size + test_size <= len(ordered):
        train = ordered[start : start + train_size]
        test = ordered[start + train_size : start + train_size + test_size]
        train_result = replay_factor(train, factor)
        test_result = replay_factor(test, factor)
        windows.append({"train": train_result, "test": test_result})
        start += test_size
    if not windows:
        return {"status": "LOW_SAMPLE", "windows": [], "oos_mean_return": None}
    oos = [w["test"]["mean_return"] for w in windows if w["test"]["mean_return"] is not None]
    return {
        "status": "COMPLETE" if len(oos) >= 2 else "LOW_SAMPLE",
        "windows": windows,
        "oos_mean_return": round(sum(oos) / len(oos), 8) if oos else None,
        "oos_windows": len(oos),
        "production_eligible": False,
        "reason": "research_only_until_live_sample_validation",
    }
