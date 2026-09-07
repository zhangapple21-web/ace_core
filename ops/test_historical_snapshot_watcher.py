import json

from core.historical_snapshot_watcher import watch_once
from core.historical_factor_replay import run_replay


def _rows(sessions=24, symbols=("AAA", "BBB", "CCC", "DDD")):
    rows = []
    for day in range(sessions):
        for offset, symbol in enumerate(symbols):
            close = 10 + offset + day * (0.08 + offset * 0.01)
            rows.append({"timestamp": f"2026-01-{day + 1:02d}", "symbol": symbol, "open": close - 0.1, "high": close + 0.2, "low": close - 0.2, "close": close, "volume": 1000 + day * 10})
    return rows


def _metadata():
    return {"source_refs": ["source://fixture"], "lineage_observable": True, "point_in_time_rule": "features_at_t_only", "cross_source_consistency": True, "cost_model": {"version": "v1", "commission_bps": 3, "slippage_bps": 5}, "out_of_sample_split": {"train": "2026-01-01/10", "validation": "2026-01-11/17", "test": "2026-01-18/24"}}


def test_watcher_auto_activates_eligible_json_and_deduplicates(tmp_path):
    root = tmp_path / "incoming"
    root.mkdir()
    valid = root / "valid.json"
    valid.write_text(json.dumps({"metadata": _metadata(), "rows": _rows()}), encoding="utf-8")
    invalid = root / "benchmark.json"
    invalid.write_text(json.dumps({"summary": {"sources": {"pytdx": {}}}}), encoding="utf-8")
    duplicate = root / "benchmark_copy.json"
    duplicate.write_bytes(invalid.read_bytes())
    state, report = tmp_path / "state.json", tmp_path / "report.json"

    first = watch_once(root, state, report)
    assert first["scanned_count"] == 3
    assert first["replay_invoked_count"] == 1
    assert any(item["status"] == "NO_ELIGIBLE_HISTORICAL_SNAPSHOT" for item in first["entries"])
    assert any(item["status"] == "DUPLICATE_CONTENT" for item in first["entries"])
    second = watch_once(root, state, report)
    assert second["new_or_changed_count"] == 0
    assert second["replay_invoked_count"] == 0


def test_watcher_refuses_tabular_without_metadata_sidecar(tmp_path):
    root = tmp_path / "incoming"
    root.mkdir()
    csv_path = root / "snapshot.csv"
    csv_path.write_text("timestamp,symbol,open,high,low,close,volume\n2026-01-01,AAA,1,1.1,0.9,1,100\n", encoding="utf-8")
    report = watch_once(root, tmp_path / "state.json", tmp_path / "report.json")
    assert report["entries"][0]["reason"] == "metadata_sidecar_missing"


