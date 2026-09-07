"""Run the read-only historical factor replay against an explicit snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.historical_factor_replay import run_replay, write_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = run_replay(args.input)
    write_report(report, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in {"REPLAY_COMPLETED", "NO_ELIGIBLE_HISTORICAL_SNAPSHOT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())


