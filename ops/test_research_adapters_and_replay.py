"""Contract tests for real-data adapters and leakage-aware replay."""

from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.factor_replay import replay_factor, walk_forward_validate  # noqa: E402
from core.research_data_adapter import fetch_tencent_daily, fetch_tencent_quote  # noqa: E402


class _Response:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


class ResearchAdaptersAndReplayTests(unittest.TestCase):
    def test_quote_adapter_normalizes_payload(self):
        fields = [""] * 40
        fields[0:7] = ["51", "TEST", "000001", "10.00", "9.90", "9.95", "100"]
        fields[30:35] = ["20260916100000", "0.10", "1.01", "10.20", "9.80"]
        fields[37:40] = ["1000", "2.0", "1"]
        body = 'v_sz000001="' + "~".join(fields) + '";'
        result = fetch_tencent_quote("000001", opener=lambda *_args, **_kwargs: _Response(body))
        self.assertEqual(result["code"], "000001")
        self.assertEqual(result["price"], 10.0)

    def test_daily_adapter_normalizes_rows(self):
        payload = {"data": {"sz000001": {"qfqday": [["2026-09-15", "1", "2", "3", "0.5", "100"]]}}}
        body = "ace_kline=" + json.dumps(payload)
        result = fetch_tencent_daily("sz000001", opener=lambda *_args, **_kwargs: _Response(body))
        self.assertEqual(result["rows"][0]["close"], 2.0)

    def test_replay_rejects_future_feature_rows(self):
        rows = [
            {"feature_time": "2026-09-01", "outcome_time": "2026-09-02", "x": 1, "forward_return": 0.1},
            {"feature_time": "2026-09-03", "outcome_time": "2026-09-02", "x": 9, "forward_return": 9.9},
        ]
        result = replay_factor(rows, lambda row: row["x"])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_walk_forward_stays_non_production(self):
        rows = []
        for i in range(8):
            rows.append({"feature_time": f"2026-09-{i + 1:02d}", "outcome_time": f"2026-10-{i + 1:02d}", "x": i, "forward_return": 0.01 if i % 2 else -0.01})
        result = walk_forward_validate(rows, lambda row: row["x"], train_size=2, test_size=2)
        self.assertFalse(result["production_eligible"])
        self.assertEqual(result["status"], "COMPLETE")


if __name__ == "__main__":
    unittest.main()
