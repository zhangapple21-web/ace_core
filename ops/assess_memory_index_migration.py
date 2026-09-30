"""评估旧 MemoryIndex 是否适合迁移到 Memory Kernel，不执行迁移。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


REPLACEMENT_THRESHOLDS = {
    "minimum_labeled_queries": 300,
    "minimum_queries_per_stratum": 50,
    "query_strata": ["general", "temporal", "conflict", "provenance", "privacy", "unknown"],
    "recall_at_5_min": 0.90,
    "max_recall_at_5_regression_vs_legacy": 0.02,
    "max_mrr_at_10_regression_vs_legacy": 0.02,
    "max_precision_at_5_regression_vs_legacy": 0.02,
    "conflict_retention_rate_min": 1.0,
    "unknown_abstention_rate_min": 1.0,
    "p99_latency_ms_hard_cap": 250.0,
    "p99_latency_legacy_multiplier_max": 1.25,
    "privacy_leak_count_max": 0,
    "minimum_concurrent_reads": 100,
    "minimum_concurrent_writes": 10,
    "minimum_crash_injection_points": 3,
    "rollback_data_basis_required": "REAL_PRIVATE_DATA_OFFLINE_COPY",
    "rollback_lost_acknowledged_writes_max": 0,
    "rollback_duration_minutes_max": 5.0,
}
_REPLACEMENT_EVIDENCE_FIELDS = (
    "query_count",
    "query_strata_counts",
    "recall_at_5",
    "recall_delta_vs_legacy_at_5",
    "mrr_delta_vs_legacy_at_10",
    "precision_delta_vs_legacy_at_5",
    "conflict_retention_rate",
    "unknown_abstention_rate",
    "p99_latency_ms",
    "legacy_p99_latency_ms",
    "privacy_leak_count",
    "boundary_tests_passed",
    "concurrent_read_count",
    "concurrent_write_count",
    "crash_injection_points_passed",
    "rollback_data_basis",
    "rollback_source_sha256",
    "rollback_restored_sha256",
    "rollback_lost_acknowledged_writes",
    "rollback_duration_minutes",
)


def evaluate_replacement_evidence(evidence: dict | None) -> dict:
    """Evaluate pre-registered cutover thresholds; this does not authenticate evidence."""

    if not isinstance(evidence, dict):
        return {
            "status": "REVIEW_REQUIRED",
            "missing_evidence": list(_REPLACEMENT_EVIDENCE_FIELDS),
            "failed_gates": [],
            "thresholds": REPLACEMENT_THRESHOLDS,
            "evidence_authenticated": False,
        }

    missing = [field for field in _REPLACEMENT_EVIDENCE_FIELDS if field not in evidence]
    if missing:
        return {
            "status": "REVIEW_REQUIRED",
            "missing_evidence": missing,
            "failed_gates": [],
            "thresholds": REPLACEMENT_THRESHOLDS,
            "evidence_authenticated": False,
        }

    failed: list[str] = []
    try:
        query_count = int(evidence["query_count"])
        parsed_strata = {
            name: int(evidence["query_strata_counts"].get(name, 0))
            for name in REPLACEMENT_THRESHOLDS["query_strata"]
        }
        numeric = {
            field: float(evidence[field])
            for field in (
                "recall_at_5",
                "recall_delta_vs_legacy_at_5",
                "mrr_delta_vs_legacy_at_10",
                "precision_delta_vs_legacy_at_5",
                "conflict_retention_rate",
                "unknown_abstention_rate",
                "p99_latency_ms",
                "legacy_p99_latency_ms",
                "rollback_duration_minutes",
            )
        }
        integer = {
            field: int(evidence[field])
            for field in (
                "privacy_leak_count",
                "concurrent_read_count",
                "concurrent_write_count",
                "crash_injection_points_passed",
                "rollback_lost_acknowledged_writes",
            )
        }
    except (TypeError, ValueError, OverflowError, AttributeError):
        return {
            "status": "REVIEW_REQUIRED",
            "missing_evidence": [],
            "failed_gates": ["metric_type_invalid"],
            "thresholds": REPLACEMENT_THRESHOLDS,
            "evidence_authenticated": False,
        }
    if any(not math.isfinite(value) for value in numeric.values()):
        return {
            "status": "REVIEW_REQUIRED",
            "missing_evidence": [],
            "failed_gates": ["non_finite_metric"],
            "thresholds": REPLACEMENT_THRESHOLDS,
            "evidence_authenticated": False,
        }
    for field in ("recall_at_5", "conflict_retention_rate", "unknown_abstention_rate"):
        if numeric[field] < 0.0 or numeric[field] > 1.0:
            return {
                "status": "REVIEW_REQUIRED",
                "missing_evidence": [],
                "failed_gates": [f"{field}_out_of_range"],
                "thresholds": REPLACEMENT_THRESHOLDS,
                "evidence_authenticated": False,
            }
    if numeric["legacy_p99_latency_ms"] <= 0 or numeric["rollback_duration_minutes"] < 0:
        return {
            "status": "REVIEW_REQUIRED",
            "missing_evidence": [],
            "failed_gates": ["latency_or_duration_out_of_range"],
            "thresholds": REPLACEMENT_THRESHOLDS,
            "evidence_authenticated": False,
        }

    strata = evidence["query_strata_counts"]
    if not isinstance(strata, dict):
        failed.append("query_strata_counts_invalid")
        strata = {}
    if query_count < REPLACEMENT_THRESHOLDS["minimum_labeled_queries"]:
        failed.append("query_count_below_minimum")
    if any(parsed_strata[name] < REPLACEMENT_THRESHOLDS["minimum_queries_per_stratum"] for name in parsed_strata):
        failed.append("query_stratum_below_minimum")
    if sum(parsed_strata.values()) != query_count:
        failed.append("query_strata_total_mismatch")
    if numeric["recall_at_5"] < REPLACEMENT_THRESHOLDS["recall_at_5_min"]:
        failed.append("recall_at_5_below_minimum")
    if numeric["recall_delta_vs_legacy_at_5"] < -REPLACEMENT_THRESHOLDS["max_recall_at_5_regression_vs_legacy"]:
        failed.append("recall_regression_exceeded")
    if numeric["mrr_delta_vs_legacy_at_10"] < -REPLACEMENT_THRESHOLDS["max_mrr_at_10_regression_vs_legacy"]:
        failed.append("mrr_regression_exceeded")
    if numeric["precision_delta_vs_legacy_at_5"] < -REPLACEMENT_THRESHOLDS["max_precision_at_5_regression_vs_legacy"]:
        failed.append("precision_regression_exceeded")
    if numeric["conflict_retention_rate"] < REPLACEMENT_THRESHOLDS["conflict_retention_rate_min"]:
        failed.append("conflict_retention_below_100_percent")
    if numeric["unknown_abstention_rate"] < REPLACEMENT_THRESHOLDS["unknown_abstention_rate_min"]:
        failed.append("unknown_abstention_below_100_percent")
    p99 = numeric["p99_latency_ms"]
    legacy_p99 = numeric["legacy_p99_latency_ms"]
    latency_cap = min(
        REPLACEMENT_THRESHOLDS["p99_latency_ms_hard_cap"],
        legacy_p99 * REPLACEMENT_THRESHOLDS["p99_latency_legacy_multiplier_max"],
    )
    if p99 > latency_cap:
        failed.append("p99_latency_gate_failed")
    if integer["privacy_leak_count"] > REPLACEMENT_THRESHOLDS["privacy_leak_count_max"]:
        failed.append("privacy_leak_detected")
    if evidence["boundary_tests_passed"] is not True:
        failed.append("boundary_tests_failed")
    if integer["concurrent_read_count"] < REPLACEMENT_THRESHOLDS["minimum_concurrent_reads"]:
        failed.append("concurrent_read_coverage_below_minimum")
    if integer["concurrent_write_count"] < REPLACEMENT_THRESHOLDS["minimum_concurrent_writes"]:
        failed.append("concurrent_write_coverage_below_minimum")
    if integer["crash_injection_points_passed"] < REPLACEMENT_THRESHOLDS["minimum_crash_injection_points"]:
        failed.append("crash_recovery_coverage_below_minimum")
    source_hash = str(evidence["rollback_source_sha256"] or "").lower()
    restored_hash = str(evidence["rollback_restored_sha256"] or "").lower()
    if evidence["rollback_data_basis"] != REPLACEMENT_THRESHOLDS["rollback_data_basis_required"]:
        failed.append("rollback_not_tested_on_real_private_data_copy")
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash) or source_hash != restored_hash:
        failed.append("rollback_hash_mismatch_or_missing")
    if integer["rollback_lost_acknowledged_writes"] > REPLACEMENT_THRESHOLDS["rollback_lost_acknowledged_writes_max"]:
        failed.append("rollback_lost_acknowledged_writes")
    rollback_minutes = numeric["rollback_duration_minutes"]
    if rollback_minutes > REPLACEMENT_THRESHOLDS["rollback_duration_minutes_max"]:
        failed.append("rollback_duration_exceeded")

    return {
        "status": "METRICS_PASS_REVIEW_REQUIRED" if not failed else "FAIL",
        "missing_evidence": [],
        "failed_gates": failed,
        "thresholds": REPLACEMENT_THRESHOLDS,
        "observed_latency_cap_ms": latency_cap,
        "evidence_authenticated": False,
    }


def _load_receipt(path: Path | None) -> dict | None:
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _caller_status(receipt: dict | None, repo_root: Path) -> dict:
    if not isinstance(receipt, dict):
        return {"status": "NOT_EVALUATED", "facade": "MemoryGateway", "evidence_authenticated": False}
    daemon_path = repo_root / "ace_daemon.py"
    cli_path = repo_root / "ace.py"
    try:
        daemon_sha = hashlib.sha256(daemon_path.read_bytes()).hexdigest()
        cli_sha = hashlib.sha256(cli_path.read_bytes()).hexdigest()
    except OSError:
        return {"status": "STALE_OR_UNREADABLE", "facade": "MemoryGateway", "evidence_authenticated": False}
    checks = receipt.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    expected = (
        "single_gateway_backend",
        "all_wired_consumers_share_gateway",
        "daemon_has_no_direct_memory_index_reads_or_writes",
        "candidate_kernel_not_in_daemon_path",
        "legacy_cli_fails_closed",
    )
    valid = (
        receipt.get("contract_version") == "ace.memory_gateway.caller_unification.v1"
        and receipt.get("status") == "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT"
        and receipt.get("daemon_source_sha256") == daemon_sha
        and receipt.get("cli_source_sha256") == cli_sha
        and all(checks.get(key) is True for key in expected)
        and int(receipt.get("wired_consumer_count", 0)) > 0
    )
    return {
        "status": "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT" if valid else "STALE_OR_INCOMPLETE",
        "facade": "MemoryGateway -> MemoryIndex",
        "wired_consumer_count": int(receipt.get("wired_consumer_count", 0) or 0),
        "evidence_authenticated": False,
        "receipt_ref": receipt.get("receipt_ref"),
        "source_hashes_current": receipt.get("daemon_source_sha256") == daemon_sha and receipt.get("cli_source_sha256") == cli_sha,
    }


def _rollback_status(receipt: dict | None) -> dict:
    if not isinstance(receipt, dict):
        return {
            "status": "NOT_RUN",
            "required_basis": REPLACEMENT_THRESHOLDS["rollback_data_basis_required"],
            "production_cutover_status": "NOT_RUN",
        }
    source_hash = str(receipt.get("source_sha256_at_snapshot") or "").lower()
    restored_hash = str(receipt.get("rollback_restored_sha256") or "").lower()
    valid = (
        receipt.get("status") == "PASS_REAL_PRIVATE_DATA_BACKEND_ROLLBACK_REHEARSAL"
        and receipt.get("data_basis") == "REAL_PRIVATE_DATA_OFFLINE_BACKEND_REHEARSAL"
        and bool(re.fullmatch(r"[0-9a-f]{64}", source_hash))
        and source_hash == restored_hash
        and receipt.get("source_unchanged_at_finish") is True
        and receipt.get("production_file_modified") is False
        and receipt.get("rollback_lost_baseline_records") == 0
        and receipt.get("raw_offline_copy_retained") is False
    )
    return {
        "status": "PASS_OFFLINE_COPY_REHEARSAL" if valid else "STALE_OR_INCOMPLETE",
        "required_basis": REPLACEMENT_THRESHOLDS["rollback_data_basis_required"],
        "data_basis": receipt.get("data_basis"),
        "entry_count": receipt.get("entry_count"),
        "source_sha256": source_hash,
        "restored_sha256": restored_hash,
        "production_cutover_status": "NOT_RUN",
        "receipt_authenticated": False,
    }


def assess(
    source: Path,
    *,
    repo_root: Path | None = None,
    caller_receipt: dict | None = None,
    rollback_receipt: dict | None = None,
) -> dict:
    repo_root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    caller_status = _caller_status(caller_receipt, repo_root)
    rollback_status = _rollback_status(rollback_receipt)
    if not source.exists():
        return {
            "contract_version": "ace.memory_kernel.migration_assessment.v1",
            "status": "SOURCE_MISSING",
            "source": str(source),
            "caller_unification": caller_status,
            "real_data_rollback": rollback_status,
            "replacement_gate": evaluate_replacement_evidence(None),
            "execution_authorized": False,
            "production_integration": False,
        }
    data = json.loads(source.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else []
    entries = [item for item in entries if isinstance(item, dict)]
    types = Counter(str(item.get("type") or "UNKNOWN") for item in entries)
    classes = Counter(str(item.get("data_class") or "UNKNOWN") for item in entries)
    with_source = sum(bool(item.get("source_path")) for item in entries)
    total = len(entries)
    decision = "READY_FOR_BOUNDED_MIGRATION"
    reasons = []
    if total > 500:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("legacy_index_large")
    if total and with_source / total < 0.5:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("source_coverage_below_50_percent")
    if classes.get("PRIVATE", 0) == total and total:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("all_records_private")
    return {
        "contract_version": "ace.memory_kernel.migration_assessment.v1",
        "status": decision,
        "source": str(source),
        "entry_count": total,
        "type_counts": dict(types),
        "data_class_counts": dict(classes),
        "source_path_count": with_source,
        "source_coverage": (with_source / total) if total else 0.0,
        "latest_created_at": max((str(item.get("created_at") or "") for item in entries), default=None),
        "reasons": reasons,
        "action": "只迁移有来源和明确用途的受治理切片；不把日常摘要批量当作事实导入",
        "caller_unification": caller_status,
        "real_data_rollback": rollback_status,
        "replacement_gate": evaluate_replacement_evidence(None),
        "execution_authorized": False,
        "production_integration": False,
        "promotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("06_RUNTIME/ace/data/memory/memory_index.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    evidence_root = repo_root / "08_GOVERNANCE" / "evidence"
    caller_receipt = _load_receipt(evidence_root / "memory_gateway_caller_unification_20260928.json")
    rollback_receipt = _load_receipt(
        repo_root / "06_RUNTIME" / "ace" / "data" / "memory" / "evidence" / "real_memory_backend_rollback_20260929.json"
    )
    report = assess(args.source, repo_root=repo_root, caller_receipt=caller_receipt, rollback_receipt=rollback_receipt)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
