"""Pure research-layer technical feature contract.

This module deliberately has no provider, TaskPool, Advisor, Risk, or Telegram
dependency. It transforms an already-admitted OHLCV research snapshot into
descriptive market-state features only; it never emits a recommendation.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "financial_technical_features.v1"


def _number(value: Any) -> float:
    value = float(value)
    if not isfinite(value):
        raise ValueError("OHLCV values must be finite")
    return value


def _ema(values: Sequence[float], period: int) -> list[float]:
    if len(values) < period:
        return []
    result = [sum(values[:period]) / period]
    alpha = 2 / (period + 1)
    for value in values[period:]:
        result.append((value - result[-1]) * alpha + result[-1])
    return result


def _rsi(values: Sequence[float], period: int) -> float:
    if len(values) <= period:
        raise ValueError(f"at least {period + 1} closes required for RSI{period}")
    changes = [values[index] - values[index - 1] for index in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for index in range(period, len(changes)):
        avg_gain = ((period - 1) * avg_gain + gains[index]) / period
        avg_loss = ((period - 1) * avg_loss + losses[index]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def _rsi_zone(value: float) -> str:
    if value >= 80:
        return "overbought"
    if value >= 60:
        return "strong"
    if value >= 40:
        return "neutral"
    if value >= 20:
        return "weak"
    return "oversold"


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(value, digits)


def build_technical_feature_set(
    ohlcv: Sequence[Mapping[str, Any]],
    provenance: Mapping[str, Any],
    *,
    symbol: str,
) -> dict[str, Any]:
    required_provenance = (
        "data_snapshot_hash", "as_of", "source_refs", "freshness",
        "coverage", "cross_source_consistency",
    )
    missing = [key for key in required_provenance if key not in provenance]
    if missing:
        raise ValueError(f"missing provenance: {', '.join(missing)}")
    if not isinstance(provenance["source_refs"], list) or not provenance["source_refs"]:
        raise ValueError("source_refs must be a non-empty list")
    if len(ohlcv) < 60:
        raise ValueError("at least 60 OHLCV rows are required")

    rows = []
    for row in ohlcv:
        rows.append({key: _number(row[key]) for key in ("open", "high", "low", "close", "volume")})
    closes = [row["close"] for row in rows]
    volumes = [row["volume"] for row in rows]
    current = closes[-1]
    moving = {f"ma{period}": sum(closes[-period:]) / period for period in (5, 10, 20, 60)}
    ma_values = [moving[f"ma{period}"] for period in (5, 10, 20)]
    if ma_values[0] > ma_values[1] > ma_values[2]:
        alignment = "bullish"
    elif ma_values[0] < ma_values[1] < ma_values[2]:
        alignment = "bearish"
    else:
        alignment = "mixed"

    fast = _ema(closes, 12)
    slow = _ema(closes, 26)
    dif_series = [fast[index + 14] - slow[index] for index in range(len(slow))]
    dea_series = _ema(dif_series, 9)
    dif = dif_series[-1]
    dea = dea_series[-1]
    prev_dif = dif_series[-2]
    prev_dea = dea_series[-2]
    if prev_dif <= prev_dea and dif > dea:
        macd_state = "bullish"
    elif prev_dif >= prev_dea and dif < dea:
        macd_state = "bearish"
    else:
        macd_state = "neutral"

    rsi_values = {f"rsi{period}": _rsi(closes, period) for period in (6, 12, 24)}
    avg_volume = sum(volumes[-6:-1]) / 5
    volume_ratio = volumes[-1] / avg_volume if avg_volume else None
    price_up = current >= closes[-2]
    if volume_ratio is None:
        volume_state = "normal"
    elif volume_ratio >= 1.5:
        volume_state = "heavy_up" if price_up else "heavy_down"
    elif volume_ratio <= 0.7:
        volume_state = "shrink_up" if price_up else "shrink_pullback"
    else:
        volume_state = "normal"

    bias = {f"bias_ma{period}": (current - moving[f"ma{period}"]) / moving[f"ma{period}"] * 100 for period in (5, 20)}
    recent_low = min(row["low"] for row in rows[-20:])
    support_levels = [
        {"name": "ma20", "value": moving["ma20"], "method": "moving_average"},
        {"name": "recent_20d_low", "value": recent_low, "method": "rolling_low"},
    ]
    invalidating = [
        "close below ma20 or recent_20d_low",
        "cross_source_consistency below recorded admission threshold",
        "freshness or coverage becomes stale/incomplete",
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "symbol": symbol,
        **{key: provenance[key] for key in required_provenance},
        "technical_features": {
            "moving_averages": {**{key: _round(value) for key, value in moving.items()}, "alignment": alignment},
            "macd": {"dif": _round(dif), "dea": _round(dea), "hist": _round((dif - dea) * 2), "state": macd_state},
            "rsi": {**{key: _round(value, 4) for key, value in rsi_values.items()}, "zone": _rsi_zone(rsi_values["rsi12"])},
            "volume": {"ratio": _round(volume_ratio, 4), "state": volume_state},
            "bias": {key: _round(value, 4) for key, value in bias.items()},
            "support_levels": [{**level, "value": _round(level["value"])} for level in support_levels],
        },
        "feature_breakdown": {
            "trend": alignment,
            "momentum": {"macd": macd_state, "rsi_zone": _rsi_zone(rsi_values["rsi12"])},
            "volume": volume_state,
            "bias": "above_ma5" if bias["bias_ma5"] >= 0 else "below_ma5",
            "support": [level["name"] for level in support_levels],
        },
        "hypothesis": "technical state is descriptive only; validate trend, momentum, volume, and support against fresh independent observations",
        "invalidating_conditions": invalidating,
        "next_verification": "recheck the same symbol and fields in the next admitted observation window",
    }
