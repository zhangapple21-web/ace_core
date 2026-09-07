#!/usr/bin/env python3
"""Run ACE's portable, fail-closed continuity audit without starting ACE."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.continuity_audit import ContinuityAuditor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--check", action="store_true", help="Read evidence only; do not append a receipt.")
    args = parser.parse_args()
    report = ContinuityAuditor(args.root).audit(record=not args.check)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # An absent predecessor is an honest bootstrap result, not a shell error.
    # Corrupt/missing anchor evidence is a distinct fail-closed audit result.
    return 2 if report["continuity_status"] == "CONTINUITY_DEGRADED" else 0


if __name__ == "__main__":
    raise SystemExit(main())

