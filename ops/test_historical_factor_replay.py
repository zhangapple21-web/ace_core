import json

from core.historical_factor_replay import load_snapshot, run_replay


def _rows(sessions=24, symbols=("AAA", "BBB", "CCC", "DDD")):
    rows = []
    for day in range(sessions):
        for offset, symbol in enumerate(symbols):
            close = 10 + offset + day * (0.08 + offset * 0.01)
            rows.append({"timestamp": f"2026-01-{day + 1:02d}", "symbol": symbol, "open": close - 0.1, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1000 + day * 10})
    return rows


def _write(path, *, metadata=None, rows=None):
    payload = {"metadata": metadata or {"source_refs": ["source://fixture"], "lineage_observable": True, "point_in_time_rule": "features_at_t_only", "cross_source_consistency": True, "cost_model": {"version": "v1", "commission_bps": 3, "slippage_bps": 5}, "out_of_sample_split": {"train": "2026-01-01/10", "validation": "2026-01-11/17", "test": "2026-01-18/24"}}, "rows": rows if rows is not None else _rows()}
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_replay_completes_and_is_non_publishing(tmp_path):
    source = tmp_path / "snapshot.json"
    _write(source)
    report = run_replay(source)
    assert report["status"] == "REPLAY_COMPLETED"
    assert report["mode"] == "FACTOR_RESEARCH_ONLY"
    assert report["production_integration"] is False
    assert report["recommendation_authority"] is False
    assert report["sessions_used"] > 0
    assert set(report["semantic_slices"]) == {"up", "down", "flat"}
    assert report["factor_contract_candidate"] is False
    assert report["factor_contract_candidate_reason"] == "execution_friction_evidence_not_available"
    assert report["execution_friction"]["evidence_status"] == "MISSING_REAL_WORLD_EXECUTION_EVIDENCE"


def test_benchmark_summary_is_rejected(tmp_path):
    source = tmp_path / "benchmark.json"
    source.write_text(json.dumps({"summary": {"sources": {"pytdx": {"availability": 1.0}}}}), encoding="utf-8")
    report = run_replay(source)
    assert report["status"] == "NO_ELIGIBLE_HISTORICAL_SNAPSHOT"
    assert "row_level_ohlcv" in report["reason"]


def test_missing_lineage_and_short_history_are_rejected(tmp_path):
    source = tmp_path / "short.json"
    _write(source, metadata={"source_refs": ["source://fixture"], "lineage_observable": False, "point_in_time_rule": "features_at_t_only"}, rows=_rows(sessions=10))
    snapshot, status = load_snapshot(source)
    assert snapshot is None
    assert status["reason"] == "lineage_not_observable"


def test_duplicate_and_invalid_ohlc_rows_are_rejected(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    rows = _rows()
    rows.append(dict(rows[0]))
    _write(duplicate, rows=rows)
    _, status = load_snapshot(duplicate)
    assert status["reason"].startswith("duplicate_row:")

    invalid = tmp_path / "invalid.json"
    rows = _rows()
    rows[0]["low"] = rows[0]["high"] + 1
    _write(invalid, rows=rows)
    _, status = load_snapshot(invalid)
    assert status["reason"] == "row_0_ohlc_relationship_invalid"


