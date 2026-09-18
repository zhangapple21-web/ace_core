"""Focused contract tests for the research-only sandbox."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.research_sandbox import (  # noqa: E402
    build_snapshot,
    classify_market_regime,
    compute_crowding,
    compute_cvar,
)


class ResearchSandboxTests(unittest.TestCase):
    def test_missing_regime_evidence_stays_unknown(self) -> None:
        result = classify_market_regime({"index_return": 0.01})
        self.assertEqual(result["regime"], "UNKNOWN")
        self.assertEqual(result["status"], "INCOMPLETE")

    def test_regime_uses_only_point_in_time_inputs(self) -> None:
        result = classify_market_regime(
            {
                "index_return": 0.01,
                "breadth_ratio": 0.65,
                "volume_ratio": 1.2,
                "realized_volatility": 0.02,
            }
        )
        self.assertEqual(result["regime"], "TREND_UP")
        self.assertEqual(result["status"], "COMPLETE")

    def test_cvar_reports_low_sample_instead_of_overclaiming(self) -> None:
        result = compute_cvar([-0.02, -0.01, 0.01, 0.03])
        self.assertEqual(result["status"], "LOW_SAMPLE")
        self.assertEqual(result["cvar"], -0.02)

    def test_crowding_requires_independent_components(self) -> None:
        result = compute_crowding({"turnover_percentile": 0.9})
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertIsNone(result["score"])

    def test_snapshot_is_research_only_and_sealed(self) -> None:
        snapshot = build_snapshot(
            observed_at="2026-09-16T15:00:00+08:00",
            observations={"market": "sample"},
            source_refs=["quote:test"],
        )
        self.assertEqual(snapshot["status"], "RESEARCH_ONLY")
        self.assertEqual(snapshot["decision"], "NO_PRODUCTION_DECISION")
        self.assertFalse(snapshot["production_integration"])
        self.assertEqual(len(snapshot["snapshot_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
