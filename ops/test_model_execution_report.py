import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.model_execution_report import collect_report


def _write_task(root, state, task_id, traces):
    path = root / "task_pool" / state / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"task_id": task_id, "outputs": {"model_execution": traces}}), encoding="utf-8")


def test_collect_report_groups_tokens_cache_cost_and_calls(tmp_path):
    _write_task(tmp_path, "archived", "RQ-1", [
        {
            "at": "2026-08-25T10:00:00",
            "task_type": "strategic",
            "provider": "shenwen",
            "selected_model": "gpt-5.6-terra",
            "role": "researcher",
            "api_result": "success",
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            "cost": {"input_usd": 0.004, "output_usd": 0.006, "total_usd": 0.01},
            "latency_ms": 100,
        },
        {
            "at": "2026-08-25T11:00:00",
            "task_type": "strategic",
            "provider": "shenwen",
            "model": "gpt-5.6-terra",
            "role": "researcher",
            "api_result": "success",
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": 80},
                "completion_tokens_details": {"reasoning_tokens": 5},
            },
            "cost": {"input_usd": 0.004, "cache_read_usd": 0.003, "output_usd": 0.013, "total_usd": 0.02},
            "latency_ms": 300,
        },
    ])
    _write_task(tmp_path, "blocked", "RQ-2", [{
        "at": "2026-08-25T12:00:00",
        "task_type": "execution",
        "provider": "shenwen",
        "selected_model": "gpt-5.4-mini",
        "role": "validator",
        "api_result": "failed",
        "usage": {},
        "cost": {},
    }])

    report = collect_report(tmp_path)

    assert report["trace_count"] == 3
    strategic = next(row for row in report["groups"] if row["task_type"] == "strategic")
    assert strategic["calls"] == 2
    assert strategic["successful_calls"] == 2
    assert strategic["input_tokens"] == 200
    assert strategic["cached_tokens"] == 80
    assert strategic["output_tokens"] == 30
    assert strategic["reasoning_tokens"] == 5
    assert strategic["input_usd"] == 0.008
    assert strategic["cache_read_usd"] == 0.003
    assert strategic["cache_write_usd"] == 0
    assert strategic["output_usd"] == 0.019
    assert strategic["total_usd"] == 0.03
    assert strategic["runtime_cost_known_calls"] == 2
    assert strategic["runtime_cost_unknown_calls"] == 0
    assert strategic["reconciled_bill_cost_calls"] == 0
    assert strategic["unreconciled_bill_cost_calls"] == 2
    assert strategic["cache_hit_rate"] == 0.4
    assert strategic["average_latency_ms"] == 200

    failed = next(row for row in report["groups"] if row["task_type"] == "execution")
    assert failed["calls"] == 1
    assert failed["failed_calls"] == 1
    assert failed["total_usd"] == 0
    assert failed["runtime_cost_unknown_calls"] == 1


def test_collect_report_keeps_unknown_and_reconciled_costs_distinct(tmp_path):
    _write_task(tmp_path, "archived", "RQ-4", [
        {
            "at": "2026-08-25T10:00:00",
            "task_type": "strategic",
            "provider": "nim",
            "selected_model": "candidate",
            "role": "researcher",
            "api_result": "success",
            "usage": {},
            "cost": {},
            "actual_provider_bill_cost": {
                "amount_usd": 0.12,
                "reconciliation_status": "reconciled",
                "bill_record_hash": "bill-a",
            },
        },
    ])

    row = collect_report(tmp_path)["groups"][0]
    assert row["runtime_cost_known_calls"] == 0
    assert row["runtime_cost_unknown_calls"] == 1
    assert row["reconciled_bill_cost_calls"] == 1
    assert row["reconciled_bill_cost_usd"] == 0.12


def test_collect_report_ignores_invalid_records_and_filters_days(tmp_path):
    _write_task(tmp_path, "archived", "RQ-3", [{
        "at": "2020-01-01T00:00:00",
        "task_type": "strategic",
        "provider": "shenwen",
        "model": "gpt-5.6-terra",
    }])
    broken = tmp_path / "task_pool" / "archived" / "broken.json"
    broken.write_text("not json", encoding="utf-8")

    assert collect_report(tmp_path, days=1)["trace_count"] == 0


def test_collect_report_scopes_future_traces_to_one_ace_local_run_and_keeps_legacy_unscoped(tmp_path):
    common = {
        "at": "2026-08-28T10:00:00",
        "task_type": "strategic",
        "provider": "shenwen",
        "selected_model": "gpt-5.6-terra",
        "role": "researcher",
        "api_result": "success",
        "usage": {},
        "cost": {},
    }
    _write_task(tmp_path, "archived", "RQ-run-a", [{**common, "ace_local_run_id": "run-A"}])
    _write_task(tmp_path, "archived", "RQ-run-b", [{**common, "ace_local_run_id": "run-B"}])
    _write_task(tmp_path, "archived", "RQ-legacy", [common])

    report = collect_report(tmp_path, ace_local_run_id="run-A")

    assert report["trace_count"] == 1
    assert report["requested_ace_local_run_id"] == "run-A"
    assert report["unscoped_trace_count"] == 1
    assert report["excluded_other_run_trace_count"] == 1
    assert report["groups"][0]["ace_local_run_id"] == "run-A"


