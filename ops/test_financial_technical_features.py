import hashlib

import pytest

from core.financial_technical_features import build_technical_feature_set


def ohlcv_fixture():
    rows = []
    close = 100.0
    for day in range(1, 81):
        close += 0.4 if day % 5 else -0.2
        rows.append({
            "date": f"2026-01-{day:02d}",
            "open": close - 0.3,
            "high": close + 0.8,
            "low": close - 0.9,
            "close": close,
            "volume": 1000 + day * 10,
        })
    return rows


def provenance():
    return {
        "data_snapshot_hash": hashlib.sha256(b"fixture").hexdigest(),
        "as_of": "2026-01-80T15:00:00+08:00",
        "source_refs": ["fixture://primary", "fixture://independent"],
        "freshness": "fixture_observed",
        "coverage": 1.0,
        "cross_source_consistency": 0.98,
    }


def test_feature_contract_contains_only_research_state_and_provenance():
    result = build_technical_feature_set(ohlcv_fixture(), provenance(), symbol="600000")

    assert set(result) == {
        "contract_version", "symbol", "data_snapshot_hash", "as_of", "source_refs",
        "freshness", "coverage", "cross_source_consistency", "technical_features",
        "feature_breakdown", "hypothesis", "invalidating_conditions", "next_verification",
    }
    assert "recommendation" not in result
    assert "signal" not in result
    assert result["data_snapshot_hash"] == provenance()["data_snapshot_hash"]
    assert result["source_refs"] == provenance()["source_refs"]


def test_ma_alignment_macd_rsi_volume_bias_support_and_breakdown():
    result = build_technical_feature_set(ohlcv_fixture(), provenance(), symbol="600000")
    features = result["technical_features"]

    assert all(features["moving_averages"][key] is not None for key in ("ma5", "ma10", "ma20", "ma60"))
    assert features["moving_averages"]["alignment"] in {"bullish", "bearish", "mixed"}
    assert features["macd"]["state"] in {"bullish", "bearish", "neutral"}
    assert all(features["rsi"][key] is not None for key in ("rsi6", "rsi12", "rsi24"))
    assert features["rsi"]["zone"] in {"overbought", "strong", "neutral", "weak", "oversold"}
    assert features["volume"]["ratio"] is not None
    assert features["volume"]["state"] in {"heavy_up", "heavy_down", "shrink_pullback", "shrink_up", "normal"}
    assert isinstance(features["bias"], dict)
    assert features["support_levels"]
    assert set(result["feature_breakdown"]) == {"trend", "momentum", "volume", "bias", "support"}
    assert result["invalidating_conditions"]
    assert result["hypothesis"]
    assert result["next_verification"]


def test_missing_provenance_is_rejected():
    with pytest.raises(ValueError, match="data_snapshot_hash"):
        build_technical_feature_set(ohlcv_fixture(), {}, symbol="600000")


def test_short_ohlcv_is_rejected_without_fabricating_features():
    with pytest.raises(ValueError, match="60"):
        build_technical_feature_set(ohlcv_fixture()[:20], provenance(), symbol="600000")
