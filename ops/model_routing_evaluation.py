#!/usr/bin/env python3
"""Read-only evidence gate for ACE model-routing upgrades.

This tool deliberately does not invoke a model, change a task, or select a
route.  It only answers whether already-persisted, admitted traces contain a
fair enough paired evaluation to justify a *separate* shadow-routing decision.

A real comparison needs an explicit ``eval_case_id`` shared by the incumbent
and candidate.  Historical tasks without this identifier remain useful
operational telemetry, but are not silently treated as a quality comparison.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


BASE_DIR = Path(__file__).resolve().parent.parent
VERIFIED_OUTCOMES = {"pass", "passed", "approved", "verified"}
REQUIRED_EVALUATION_FIELDS = (
    "evaluation_harness_id",
    "evaluation_contract_sha256",
    "eval_case_id",
    "case_manifest_sha256",
    "evidence_or_context_hash",
    "evidence_cutoff_at",
    "input_sha256",
    "harness_version",
    "provider_and_model",
    "verification_outcome",
    "verification_independent_group_id",
    "verifier_id",
    "verification_input_sha256",
)


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _admitted_trace_rows(root: Path) -> Iterable[Dict[str, Any]]:
    """Yield only persisted admitted traces; malformed records are skipped."""
    for path in sorted((root / "task_pool").glob("*/*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        outputs = task.get("outputs", {})
        if not isinstance(outputs, dict):
            continue
        admission = outputs.get("model_task_admission", {})
        if not isinstance(admission, dict) or admission.get("eligible") is not True:
            continue
        traces = outputs.get("model_execution", [])
        if not isinstance(traces, list):
            continue
        for trace in traces:
            if isinstance(trace, dict) and trace.get("api_called") is True:
                yield {"task": task, "trace": trace, "path": str(path)}


def _model(trace: Dict[str, Any]) -> str:
    return str(trace.get("selected_model") or trace.get("model") or "unknown")


def _provider_and_model(trace: Dict[str, Any]) -> str:
    provider = str(trace.get("provider") or "").strip()
    model = _model(trace).strip()
    return f"{provider}:{model}" if provider and model and model != "unknown" else ""


def _matches_route(trace: Dict[str, Any], requested: str) -> bool:
    """Match an explicit provider:model route when supplied, else a model id.

    The unqualified form remains supported for existing CLI usage, but a
    future promotion review should pass provider:model to avoid merging two
    providers that expose the same model name.
    """
    return _provider_and_model(trace) == requested if ":" in requested else _model(trace) == requested


def _evaluation_contract_issues(trace: Dict[str, Any]) -> list[str]:
    """Return fail-closed reasons why a trace is telemetry, not an eval case.

    This deliberately validates only fields explicitly persisted by an isolated
    harness.  It never derives a case from task titles, dates, or historical
    trace contents, because doing so would create a retrospective comparison.
    """
    issues = [
        f"missing_{field}"
        for field in REQUIRED_EVALUATION_FIELDS
        if not isinstance(trace.get(field), str) or not trace[field].strip()
    ]
    if trace.get("provider_and_model") != _provider_and_model(trace):
        issues.append("provider_and_model_mismatch")
    execution = trace.get("api_result_and_retry_count")
    if not isinstance(execution, dict):
        issues.append("missing_api_result_and_retry_count")
    else:
        if execution.get("api_result") != trace.get("api_result"):
            issues.append("api_result_mismatch")
        retry_count = execution.get("retry_count")
        if not isinstance(retry_count, int) or retry_count < 0:
            issues.append("invalid_retry_count")
        attempts = trace.get("attempts")
        if isinstance(attempts, list) and attempts and retry_count != len(attempts) - 1:
            issues.append("retry_count_mismatch")
    if trace.get("api_result") != "success" and not str(trace.get("failure_type") or "").strip():
        issues.append("missing_failure_type")
    return issues


def _pair_key(trace: Dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str, str, str]:
    return (
        str(trace["evaluation_harness_id"]),
        str(trace["evaluation_contract_sha256"]),
        str(trace.get("task_type") or "unknown"),
        str(trace["role"]),
        str(trace["eval_case_id"]),
        str(trace["case_manifest_sha256"]),
        str(trace["evidence_or_context_hash"]),
        str(trace["input_sha256"]),
        str(trace["harness_version"]),
        str(trace["evidence_cutoff_at"]),
    )


def _has_reconciled_bill_cost(trace: Dict[str, Any]) -> bool:
    billing = trace.get("actual_provider_bill_cost")
    return (
        isinstance(billing, dict)
        and isinstance(billing.get("amount_usd"), (int, float))
        and billing.get("reconciliation_status") == "reconciled"
        and isinstance(billing.get("bill_record_hash"), str)
        and bool(billing["bill_record_hash"].strip())
    )


def _summary(rows: list[Dict[str, Any]]) -> Dict[str, Any]:
    calls = len(rows)
    successes = sum(row["trace"].get("api_result") == "success" for row in rows)
    verified = sum(
        str(row["trace"].get("verification_outcome", "")).lower() in VERIFIED_OUTCOMES
        for row in rows
    )
    known_costs = [
        _number(row["trace"].get("cost", {}).get("total_usd"))
        for row in rows
        if isinstance(row["trace"].get("cost"), dict) and "total_usd" in row["trace"]["cost"]
    ]
    reconciled_costs = [
        float(row["trace"]["actual_provider_bill_cost"]["amount_usd"])
        for row in rows
        if _has_reconciled_bill_cost(row["trace"])
    ]
    latencies = [_number(row["trace"].get("latency_ms")) for row in rows if row["trace"].get("latency_ms") is not None]
    return {
        "trace_count": calls,
        "successful_trace_count": successes,
        "success_rate": round(successes / calls, 6) if calls else 0.0,
        "verified_trace_count": verified,
        "verified_rate": round(verified / calls, 6) if calls else 0.0,
        "known_cost_trace_count": len(known_costs),
        "unknown_cost_trace_count": calls - len(known_costs),
        "total_known_cost_usd": round(sum(known_costs), 8),
        "reconciled_bill_cost_trace_count": len(reconciled_costs),
        "unknown_or_unreconciled_bill_cost_trace_count": calls - len(reconciled_costs),
        "total_reconciled_bill_cost_usd": round(sum(reconciled_costs), 8),
        "average_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
    }


def evaluate_routing_readiness(
    root: Path = BASE_DIR,
    *,
    baseline_model: str,
    candidate_model: str,
    minimum_verified_pairs: int = 30,
) -> Dict[str, Any]:
    """Return a non-mutating upgrade-readiness report.

    ``EVALUATION_READY`` still does not authorize production routing.  It says
    the evidence is sufficient for a governed review/canary decision.  Fewer
    than ``minimum_verified_pairs`` can only be ``SHADOW_ONLY``.
    """
    if not baseline_model or not candidate_model:
        raise ValueError("baseline_model and candidate_model are required")
    if minimum_verified_pairs < 1:
        raise ValueError("minimum_verified_pairs must be at least 1")

    rows = list(_admitted_trace_rows(Path(root)))
    baseline = [row for row in rows if _matches_route(row["trace"], baseline_model)]
    candidate = [row for row in rows if _matches_route(row["trace"], candidate_model)]

    by_case: Dict[tuple[str, ...], Dict[str, list[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    missing_case_id = 0
    incomplete_contracts: list[Dict[str, Any]] = []
    for route_label, route_rows in (("baseline", baseline), ("candidate", candidate)):
        for row in route_rows:
            trace = row["trace"]
            case_id = str(trace.get("eval_case_id") or "").strip()
            if not case_id:
                missing_case_id += 1
                continue
            issues = _evaluation_contract_issues(trace)
            if issues:
                incomplete_contracts.append({
                    "task_id": row["task"].get("task_id", ""),
                    "eval_case_id": case_id,
                    "model": _provider_and_model(trace) or _model(trace),
                    "issues": issues,
                })
                continue
            by_case[_pair_key(trace)][route_label].append(row)

    comparisons = []
    missing_verification = 0
    missing_reconciled_bill_cost = 0
    ambiguous_cases: list[Dict[str, Any]] = []
    for (
        harness_id,
        contract_hash,
        task_type,
        role,
        case_id,
        manifest_hash,
        evidence_hash,
        input_hash,
        harness_version,
        evidence_cutoff_at,
    ), grouped in sorted(by_case.items()):
        left, right = grouped.get("baseline", []), grouped.get("candidate", [])
        if not left or not right:
            continue
        if len(left) != 1 or len(right) != 1:
            ambiguous_cases.append({
                "eval_case_id": case_id,
                "task_type": task_type,
                "role": role,
                "baseline_trace_count": len(left),
                "candidate_trace_count": len(right),
            })
            continue
        verified = all(
            str(row["trace"].get("verification_outcome", "")).lower() in VERIFIED_OUTCOMES
            for row in [*left, *right]
        )
        if not verified:
            missing_verification += 1
        reconciled_cost = all(_has_reconciled_bill_cost(row["trace"]) for row in [*left, *right])
        if not reconciled_cost:
            missing_reconciled_bill_cost += 1
        comparisons.append({
            "eval_case_id": case_id,
            "task_type": task_type,
            "role": role,
            "evaluation_harness_id": harness_id,
            "evaluation_contract_sha256": contract_hash,
            "case_manifest_sha256": manifest_hash,
            "evidence_or_context_hash": evidence_hash,
            "input_sha256": input_hash,
            "harness_version": harness_version,
            "evidence_cutoff_at": evidence_cutoff_at,
            "baseline": baseline_model,
            "candidate": candidate_model,
            "baseline_success_rate": _summary(left)["success_rate"],
            "candidate_success_rate": _summary(right)["success_rate"],
            "baseline_verified": _summary(left)["verified_rate"] == 1.0,
            "candidate_verified": _summary(right)["verified_rate"] == 1.0,
            "verified": verified,
            "reconciled_bill_cost": reconciled_cost,
        })

    verified_pairs = sum(item["verified"] for item in comparisons)
    if incomplete_contracts:
        decision, reasons = "UPGRADE_BLOCKED", ["INCOMPLETE_EVALUATION_CONTRACT"]
    elif ambiguous_cases:
        decision, reasons = "UPGRADE_BLOCKED", ["AMBIGUOUS_CASE_CARDINALITY"]
    elif not comparisons:
        decision, reasons = "UPGRADE_BLOCKED", ["NO_MATCHED_EVALUATION_CASES"]
    elif missing_verification:
        decision, reasons = "UPGRADE_BLOCKED", ["MATCHED_CASES_MISSING_VERIFICATION"]
    elif verified_pairs < minimum_verified_pairs:
        decision, reasons = "SHADOW_ONLY", ["INSUFFICIENT_VERIFIED_PAIRED_CASES"]
    elif missing_reconciled_bill_cost:
        decision, reasons = "UPGRADE_BLOCKED", ["MATCHED_CASES_MISSING_RECONCILED_BILL_COST"]
    else:
        decision, reasons = "EVALUATION_READY", ["VERIFIED_PAIRED_CASE_THRESHOLD_MET"]

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only_historical_evidence",
        "routing_effect": False,
        "baseline_model": baseline_model,
        "candidate_model": candidate_model,
        "minimum_verified_pairs": minimum_verified_pairs,
        "decision": decision,
        "reason_codes": reasons,
        "coverage": {
            "admitted_trace_count": len(rows),
            "baseline_trace_count": len(baseline),
            "candidate_trace_count": len(candidate),
            "paired_case_count": len(comparisons),
            "verified_paired_case_count": verified_pairs,
            "selected_trace_missing_eval_case_id": missing_case_id,
            "selected_trace_incomplete_evaluation_contract": len(incomplete_contracts),
            "ambiguous_case_count": len(ambiguous_cases),
        },
        "baseline_metrics": _summary(baseline),
        "candidate_metrics": _summary(candidate),
        "comparisons": comparisons,
        "incomplete_evaluation_contracts": incomplete_contracts,
        "ambiguous_cases": ambiguous_cases,
        "required_future_trace_fields": [
            "evaluation_harness_id",
            "evaluation_contract_sha256",
            "eval_case_id",
            "case_manifest_sha256",
            "evidence_or_context_hash",
            "evidence_cutoff_at",
            "input_sha256",
            "harness_version",
            "provider_and_model",
            "api_result_and_retry_count",
            "verification_outcome",
            "verification_independent_group_id",
            "verifier_id",
            "verification_input_sha256",
            "latency_ms",
            "actual_provider_bill_cost",
            "failure_type",
        ],
        "next_action": (
            "create no production tasks; attach the listed fields only when an existing admitted task "
            "is voluntarily evaluated in an isolated shadow harness"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only ACE model-routing upgrade evidence gate")
    parser.add_argument("--root", type=Path, default=BASE_DIR)
    parser.add_argument("--baseline-model", required=True)
    parser.add_argument("--candidate-model", required=True)
    parser.add_argument("--minimum-verified-pairs", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = evaluate_routing_readiness(
        args.root,
        baseline_model=args.baseline_model,
        candidate_model=args.candidate_model,
        minimum_verified_pairs=args.minimum_verified_pairs,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
