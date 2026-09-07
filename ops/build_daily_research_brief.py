"""Build one local, teacher-review research brief from ACE evidence.

This command has no network, Advisor, Risk, Telegram, or broker dependency.
It persists only the research artifact requested by the caller.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.daily_research_brief import build_daily_research_brief, write_brief


EVIDENCE_DIR = ROOT / "06_RUNTIME" / "ace" / "data" / "stock_data_evidence"


def _read_mapping(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def build_from_runtime(now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    benchmark = _read_mapping(EVIDENCE_DIR / "stock_data_benchmark_latest.json")
    matrix = _read_mapping(EVIDENCE_DIR / "A_SHARE_DATA_CAPABILITY_MATRIX.json")
    summary = benchmark.get("summary", {}) if isinstance(benchmark.get("summary"), dict) else {}
    # The runtime benchmark alone is not a real-time quote decision.  Absence of
    # an explicit runtime DataQualityDecision therefore closes the brief.
    quality = {
        "data_quality_status": "UNAVAILABLE",
        "recommendation_eligibility": "do_not_recommend",
        "reason": "no_runtime_data_quality_decision_supplied",
        "benchmark_completed_at": benchmark.get("completed_at"),
        "observed_source_count": len(summary.get("sources", {})) if isinstance(summary.get("sources"), dict) else 0,
    }
    market_date = now.astimezone(timezone.utc).date().isoformat()
    return build_daily_research_brief(
        brief_id=f"research-brief-{market_date}",
        market_date=market_date,
        generated_at=now.isoformat(),
        data_quality=quality,
        capability_matrix=matrix,
        candidates=[],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local ACE teacher-review research brief.")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs" / "research_briefs")
    args = parser.parse_args()
    brief = build_from_runtime()
    target = write_brief(args.output_dir / f"{brief['brief_id']}.json", brief)
    print(json.dumps({
        "path": str(target),
        "brief_status": brief["brief_status"],
        "candidate_count": len(brief["candidate_cards"]),
        "blockers": brief["admission"]["blockers"],
        "delivery_mode": brief["delivery"]["mode"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

