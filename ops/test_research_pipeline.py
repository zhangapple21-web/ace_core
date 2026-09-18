"""Contract tests for the auditable research pipeline skeleton."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_pipeline import (  # noqa: E402
    build_evidence_bundle,
    build_research_snapshot,
    generate_factor_candidates,
    summarize_walk_forward,
)
from core.research_sandbox import write_snapshot  # noqa: E402


class ResearchPipelineTests(unittest.TestCase):
    def test_evidence_bundle_preserves_unverified_gaps(self):
        bundle = build_evidence_bundle(
            observed_at="2026-09-16T15:00:00+08:00",
            market={"payload": {"index_return": 0.01}, "status": "VERIFIED", "source_refs": ["quote:1"]},
        )
        self.assertEqual(bundle["status"], "INCOMPLETE")
        self.assertIn("funds", bundle["missing_or_unverified"])

    def test_factor_candidates_do_not_fill_missing_features(self):
        candidates = generate_factor_candidates({"return_5d": 0.03})
        self.assertEqual(candidates[0]["status"], "UNKNOWN")
        self.assertIsNone(candidates[0]["score"])

    def test_summary_is_non_production(self):
        summary = summarize_walk_forward(
            [{"oos_mean_return": 0.01, "hit_rate": 0.6}, {"oos_mean_return": -0.002, "hit_rate": 0.4}]
        )
        self.assertEqual(summary["status"], "COMPLETE")
        self.assertFalse(summary["production_eligible"])

    def test_snapshot_writes_only_after_hash_check(self):
        bundle = build_evidence_bundle(observed_at="2026-09-16T15:00:00+08:00")
        snapshot = build_research_snapshot(
            observed_at="2026-09-16T15:00:00+08:00",
            evidence_bundle=bundle,
            market_features={"index_return": 0.0, "breadth_ratio": 0.5, "volume_ratio": 1.0, "realized_volatility": 0.02},
            source_refs=["test:source"],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = write_snapshot(Path(temp_dir) / "snapshot.json", snapshot)
            self.assertEqual(result["status"], "WRITTEN_RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
