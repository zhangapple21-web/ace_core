#!/usr/bin/env python3
"""Summarize persisted model execution traces without changing task records.

Usage:
  python ops/model_execution_report.py
  python ops/model_execution_report.py --json
  python ops/model_execution_report.py --days 7
  python ops/model_execution_report.py --ace-local-run-id <run-id>
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


BASE_DIR = Path(__file__).resolve().parent.parent


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _date_from_trace(trace: Dict[str, Any], task: Dict[str, Any]) -> str:
    value = trace.get("at") or task.get("updated_at") or task.get("created_at") or "unknown"
    return str(value)[:10] if value else "unknown"


def _cached_tokens(usage: Dict[str, Any]) -> float:
    prompt_details = usage.get("prompt_tokens_details", {})
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    return _number(
        usage.get("cache_read_tokens", prompt_details.get("cached_tokens", 0))
    )


def _trace_rows(root: Path) -> Iterable[Dict[str, Any]]:
    for path in sorted((root / "task_pool").glob("*/*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        outputs = task.get("outputs", {})
        traces = outputs.get("model_execution", []) if isinstance(outputs, dict) else []
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if isinstance(trace, dict):
                yield {"task": task, "trace": trace}


def collect_report(
    root: Path = BASE_DIR,
    days: Optional[int] = None,
    ace_local_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate model traces from task_pool into stable, JSON-safe metrics."""
    cutoff = None
    if days is not None:
        cutoff = (datetime.now().date() - timedelta(days=days - 1)).isoformat()

    groups: Dict[tuple, Dict[str, Any]] = defaultdict(lambda: {
        "calls": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "input_tokens": 0.0,
        "cached_tokens": 0.0,
        "output_tokens": 0.0,
        "reasoning_tokens": 0.0,
        "input_usd": 0.0,
        "cache_read_usd": 0.0,
        "cache_write_usd": 0.0,
        "output_usd": 0.0,
        "total_usd": 0.0,
        "runtime_cost_known_calls": 0,
        "runtime_cost_unknown_calls": 0,
        "reconciled_bill_cost_calls": 0,
        "unreconciled_bill_cost_calls": 0,
        "reconciled_bill_cost_usd": 0.0,
        "latency_ms": 0.0,
    })
    trace_count = 0
    unscoped_trace_count = 0
    excluded_other_run_trace_count = 0

    for row in _trace_rows(root):
        task, trace = row["task"], row["trace"]
        date = _date_from_trace(trace, task)
        if cutoff and (date == "unknown" or date < cutoff):
            continue
        if ace_local_run_id is not None:
            trace_run_id = trace.get("ace_local_run_id")
            if not isinstance(trace_run_id, str) or not trace_run_id.strip():
                unscoped_trace_count += 1
                continue
            if trace_run_id != ace_local_run_id:
                excluded_other_run_trace_count += 1
                continue
        usage = trace.get("usage", {}) if isinstance(trace.get("usage"), dict) else {}
        cost = trace.get("cost", {}) if isinstance(trace.get("cost"), dict) else {}
        completion_details = usage.get("completion_tokens_details", {})
        if not isinstance(completion_details, dict):
            completion_details = {}
        key = (
            date,
            str(trace.get("task_type") or "unknown"),
            str(trace.get("provider") or "unknown"),
            str(trace.get("selected_model") or trace.get("model") or "unknown"),
            str(trace.get("role") or "unknown"),
        )
        group = groups[key]
        group["calls"] += 1
        if trace.get("api_result") == "success":
            group["successful_calls"] += 1
        else:
            group["failed_calls"] += 1
        group["input_tokens"] += _number(usage.get("prompt_tokens"))
        group["cached_tokens"] += _cached_tokens(usage)
        group["output_tokens"] += _number(usage.get("completion_tokens"))
        group["reasoning_tokens"] += _number(completion_details.get("reasoning_tokens"))
        group["input_usd"] += _number(cost.get("input_usd"))
        group["cache_read_usd"] += _number(cost.get("cache_read_usd"))
        group["cache_write_usd"] += _number(cost.get("cache_write_usd"))
        group["output_usd"] += _number(cost.get("output_usd"))
        group["total_usd"] += _number(cost.get("total_usd"))
        if "total_usd" in cost and isinstance(cost.get("total_usd"), (int, float)):
            group["runtime_cost_known_calls"] += 1
        else:
            group["runtime_cost_unknown_calls"] += 1
        bill = trace.get("actual_provider_bill_cost", {})
        if (
            isinstance(bill, dict)
            and bill.get("reconciliation_status") == "reconciled"
            and isinstance(bill.get("amount_usd"), (int, float))
            and isinstance(bill.get("bill_record_hash"), str)
            and bill["bill_record_hash"].strip()
        ):
            group["reconciled_bill_cost_calls"] += 1
            group["reconciled_bill_cost_usd"] += float(bill["amount_usd"])
        else:
            group["unreconciled_bill_cost_calls"] += 1
        group["latency_ms"] += _number(trace.get("latency_ms"))
        trace_count += 1

    rows = []
    for key, metrics in sorted(groups.items()):
        date, task_type, provider, model, role = key
        rows.append({
            "date": date,
            "task_type": task_type,
            "provider": provider,
            "model": model,
            "role": role,
            **({"ace_local_run_id": ace_local_run_id} if ace_local_run_id is not None else {}),
            **{name: round(value, 6) if isinstance(value, float) else value for name, value in metrics.items()},
            "cache_hit_rate": round(metrics["cached_tokens"] / metrics["input_tokens"], 6)
            if metrics["input_tokens"] else 0.0,
            "average_latency_ms": round(metrics["latency_ms"] / metrics["calls"], 2)
            if metrics["calls"] else 0.0,
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "days": days,
        "requested_ace_local_run_id": ace_local_run_id,
        "trace_count": trace_count,
        "unscoped_trace_count": unscoped_trace_count,
        "excluded_other_run_trace_count": excluded_other_run_trace_count,
        "groups": rows,
    }


def print_text(report: Dict[str, Any]) -> None:
    print(f"Model execution report: {report['trace_count']} calls")
    if not report["groups"]:
        print("No matching model execution traces.")
        return
    print("date       task_type          provider  model              role       calls ok fail cache% cache_usd total_usd avg_ms")
    for row in report["groups"]:
        print(
            f"{row['date']:<10} {row['task_type']:<18.18} {row['provider']:<9.9} "
            f"{row['model']:<18.18} {row['role']:<10.10} {row['calls']:>5} "
            f"{row['successful_calls']:>2} {row['failed_calls']:>4} "
            f"{row['cache_hit_rate'] * 100:>5.1f} {row['cache_read_usd']:>9.6f} {row['total_usd']:>9.6f} "
            f"{row['average_latency_ms']:>6.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate persisted ACE model execution traces")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help="ACE root containing task_pool")
    parser.add_argument("--days", type=int, help="Include only the latest N calendar days")
    parser.add_argument("--ace-local-run-id", help="Filter future traces to one ACE-local daemon run")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a text table")
    args = parser.parse_args()
    if args.days is not None and args.days < 1:
        parser.error("--days must be at least 1")
    report = collect_report(args.root, args.days, args.ace_local_run_id)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)


if __name__ == "__main__":
    main()

