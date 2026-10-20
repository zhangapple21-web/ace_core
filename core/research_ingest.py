"""Point-in-time ingestion entry point for one research snapshot.

The collector is intentionally conservative: only quote and daily-bar data
are fetched by the built-in Tencent adapter.  Sector, funds and announcements
remain explicitly unverified until independent adapters are connected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Callable, Mapping

from .research_data_adapter import fetch_tencent_daily, fetch_tencent_quote
from .research_pipeline import build_evidence_bundle, build_research_snapshot
from .research_sandbox import write_snapshot


def _returns(closes: list[float]) -> list[float]:
    return [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes)) if closes[index - 1]]


def derive_features(quote: Mapping[str, Any], daily: Mapping[str, Any]) -> dict[str, Any]:
    """Derive only fields supported by the captured quote/daily bars."""

    rows = [row for row in daily.get("rows", []) if isinstance(row, Mapping)]
    closes = [float(row["close"]) for row in rows if row.get("close") is not None]
    volumes = [float(row["volume"]) for row in rows if row.get("volume") is not None]
    features: dict[str, Any] = {}
    if len(closes) >= 6:
        features["return_5d"] = closes[-1] / closes[-6] - 1.0
    if len(closes) >= 20 and mean(closes[-20:]):
        features["close_vs_ma20"] = closes[-1] / mean(closes[-20:]) - 1.0
    if len(volumes) >= 21 and mean(volumes[-21:-1]):
        features["volume_ratio"] = volumes[-1] / mean(volumes[-21:-1])
    daily_returns = _returns(closes[-21:])
    if len(daily_returns) >= 10:
        features["realized_volatility"] = pstdev(daily_returns)
    if quote.get("change_pct") is not None:
        # Tencent reports this field in percentage points, while the research
        # contract stores returns as decimals.
        features["price_change_pct"] = float(quote["change_pct"]) / 100.0
    return features


def ingest_symbol_snapshot(
    symbol: str,
    *,
    output_dir: str | Path,
    quote_fetcher: Callable[..., dict[str, Any]] = fetch_tencent_quote,
    daily_fetcher: Callable[..., dict[str, Any]] = fetch_tencent_daily,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch, seal and write one symbol snapshot; always returns research-only."""

    quote = quote_fetcher(symbol)
    daily = daily_fetcher(symbol, days=90)
    captured_at = (now or datetime.now(timezone(timedelta(hours=8)))).isoformat()
    normalized_symbol = str(quote.get("symbol") or symbol).lower()
    source_refs = [
        f"{quote.get('provider', 'unknown')}:quote:{normalized_symbol}",
        f"{daily.get('provider', 'unknown')}:daily:{normalized_symbol}:qfq",
    ]
    evidence = build_evidence_bundle(
        observed_at=captured_at,
        market={
            "payload": {"quote": dict(quote), "daily": dict(daily)},
            "status": "VERIFIED",
            "source_refs": source_refs,
            "coverage": 1.0,
        },
        sector={"payload": {"reason": "sector_adapter_not_connected"}, "status": "UNVERIFIED"},
        funds={"payload": {"reason": "funds_adapter_not_connected"}, "status": "UNVERIFIED"},
        announcements={
            "payload": {"reason": "announcement_adapter_not_connected"},
            "status": "UNVERIFIED",
        },
    )
    features = derive_features(quote, daily)
    snapshot = build_research_snapshot(
        observed_at=captured_at,
        evidence_bundle=evidence,
        market_features=features,
        crowding_features={},
        factor_features=features,
        source_refs=source_refs,
    )
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    target = Path(output_dir) / f"{normalized_symbol}_{stamp}.json"
    write_result = write_snapshot(target, snapshot)
    return {
        "status": "RESEARCH_ONLY",
        "symbol": normalized_symbol,
        "snapshot": snapshot,
        "write": write_result,
    }
