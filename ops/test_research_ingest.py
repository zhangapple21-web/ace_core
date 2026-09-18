"""Contract tests for point-in-time research ingestion."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_ingest import ingest_symbol_snapshot  # noqa: E402


class ResearchIngestTests(unittest.TestCase):
    def test_ingest_writes_hash_sealed_research_record(self):
        quote = {
            "provider": "fixture",
            "symbol": "sz000001",
            "code": "000001",
            "price": 10.0,
            "change_pct": 1.0,
            "evidence_status": "VERIFIED",
        }
        rows = [
            {"date": f"2026-09-{index:02d}", "open": 1, "close": float(index), "high": 1, "low": 1, "volume": 100}
            for index in range(1, 31)
        ]
        daily = {"provider": "fixture", "symbol": "sz000001", "frequency": "1d", "adjustment": "qfq", "rows": rows}
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ingest_symbol_snapshot(
                "000001",
                output_dir=temp_dir,
                quote_fetcher=lambda _symbol: quote,
                daily_fetcher=lambda _symbol, days=90: daily,
                now=datetime(2026, 9, 16, tzinfo=timezone.utc),
            )
            self.assertEqual(result["status"], "RESEARCH_ONLY")
            self.assertTrue(Path(result["write"]["path"]).exists())
            self.assertFalse(result["snapshot"]["production_integration"])
            self.assertIn("sector", result["snapshot"]["observations"]["evidence_bundle"]["missing_or_unverified"])


if __name__ == "__main__":
    unittest.main()
