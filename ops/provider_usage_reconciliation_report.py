#!/usr/bin/env python3
"""Generate a redacted, read-only provider usage reconciliation report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.provider_usage_reconciliation import build_usage_report, find_latest_usage_csv, safe_source_error_status


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only redacted provider usage reconciliation")
    parser.add_argument("--input", type=Path, help="Specific exported usage CSV (read-only)")
    parser.add_argument("--downloads-dir", type=Path, default=Path.home() / "Downloads")
    parser.add_argument("--runtime-state", type=Path, help="Optional ACE daemon state for aggregate-only scope comparison")
    parser.add_argument("--minimum-failure-burst", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Print the complete redacted JSON report")
    args = parser.parse_args()

    source = args.input or find_latest_usage_csv(args.downloads_dir)
    if source is None:
        print(json.dumps({"status": "NO_SOURCE"}, ensure_ascii=False))
        return

    runtime_daily_cost = None
    if args.runtime_state:
        try:
            state = json.loads(args.runtime_state.read_text(encoding="utf-8"))
            runtime_daily_cost = state.get("shenwen_daily_cost", {}) if isinstance(state, dict) else {}
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"Cannot read runtime state: {error}")

    try:
        report = build_usage_report(
            source,
            runtime_daily_cost=runtime_daily_cost,
            minimum_failure_burst=args.minimum_failure_burst,
        )
    except (OSError, ValueError) as error:
        print(json.dumps({"status": safe_source_error_status(error)}, ensure_ascii=False))
        raise SystemExit(2)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return

    totals = report["totals"]
    print("Provider usage reconciliation (read-only, aggregate-only)")
    print(f"Rows: {report['source']['row_count']} | coverage: {report['source']['actual_row_coverage']}")
    print(
        f"Completed: {totals['completed_requests']} | failed: {totals['failed_requests']} | "
        f"success: {totals['success_rate'] * 100:.2f}% | charged: ${totals['charged_usd']:.6f}"
    )
    print("Request-level billing linkage: missing; no task trace was marked reconciled.")


if __name__ == "__main__":
    main()
