import json

from ops.assess_memory_index_migration import assess, evaluate_replacement_evidence


def test_large_low_provenance_index_is_staged(tmp_path):
    source = tmp_path / "memory_index.json"
    source.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": str(index),
                        "type": "daily_summary",
                        "data_class": "PRIVATE",
                        "created_at": "2026-09-28T00:00:00Z",
                    }
                    for index in range(501)
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = assess(source)
    assert report["status"] == "STAGED_MIGRATION_REQUIRED"
    assert "legacy_index_large" in report["reasons"]
    assert report["production_integration"] is False
    assert report["replacement_gate"]["status"] == "REVIEW_REQUIRED"
    assert "rollback_source_sha256" in report["replacement_gate"]["missing_evidence"]
    assert report["caller_unification"]["status"] == "NOT_EVALUATED"
    assert report["real_data_rollback"]["status"] == "NOT_RUN"


def test_small_provenanced_index_can_be_bounded(tmp_path):
    source = tmp_path / "memory_index.json"
    source.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "one",
                        "type": "experience",
                        "data_class": "STRUCTURE",
                        "source_path": "receipt://one",
                        "created_at": "2026-09-28T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = assess(source)
    assert report["status"] == "READY_FOR_BOUNDED_MIGRATION"
    assert report["source_coverage"] == 1.0
    assert report["replacement_gate"]["status"] == "REVIEW_REQUIRED"
    assert report["caller_unification"]["facade"] == "MemoryGateway"


def test_assessment_consumes_hash_bound_caller_and_real_rollback_receipts(tmp_path):
    import hashlib

    source = tmp_path / "memory_index.json"
    source.write_text(json.dumps({"entries": []}), encoding="utf-8")
    daemon_path = tmp_path / "ace_daemon.py"
    cli_path = tmp_path / "ace.py"
    daemon_path.write_text("daemon", encoding="utf-8")
    cli_path.write_text("cli", encoding="utf-8")
    expected_checks = (
        "single_gateway_backend",
        "all_wired_consumers_share_gateway",
        "daemon_has_no_direct_memory_index_reads_or_writes",
        "candidate_kernel_not_in_daemon_path",
        "legacy_cli_fails_closed",
    )
    caller_receipt = {
        "contract_version": "ace.memory_gateway.caller_unification.v1",
        "status": "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT",
        "daemon_source_sha256": hashlib.sha256(daemon_path.read_bytes()).hexdigest(),
        "cli_source_sha256": hashlib.sha256(cli_path.read_bytes()).hexdigest(),
        "wired_consumer_count": 2,
        "checks": {key: True for key in expected_checks},
        "receipt_ref": "fixture://caller-audit",
    }
    rollback_receipt = {
        "status": "PASS_REAL_PRIVATE_DATA_BACKEND_ROLLBACK_REHEARSAL",
        "data_basis": "REAL_PRIVATE_DATA_OFFLINE_BACKEND_REHEARSAL",
        "source_sha256_at_snapshot": "a" * 64,
        "rollback_restored_sha256": "a" * 64,
        "source_unchanged_at_finish": True,
        "production_file_modified": False,
        "rollback_lost_baseline_records": 0,
        "raw_offline_copy_retained": False,
        "entry_count": 6979,
    }

    report = assess(
        source,
        repo_root=tmp_path,
        caller_receipt=caller_receipt,
        rollback_receipt=rollback_receipt,
    )

    assert report["caller_unification"]["status"] == "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT"
    assert report["real_data_rollback"]["status"] == "PASS_OFFLINE_COPY_REHEARSAL"
    assert report["real_data_rollback"]["production_cutover_status"] == "NOT_RUN"
    assert report["replacement_gate"]["status"] == "REVIEW_REQUIRED"

    daemon_path.write_text("changed daemon", encoding="utf-8")
    stale_report = assess(
        source,
        repo_root=tmp_path,
        caller_receipt=caller_receipt,
        rollback_receipt=rollback_receipt,
    )
    assert stale_report["caller_unification"]["status"] == "STALE_OR_INCOMPLETE"


def _passing_replacement_metrics():
    return {
        "query_count": 300,
        "query_strata_counts": {
            "general": 50,
            "temporal": 50,
            "conflict": 50,
            "provenance": 50,
            "privacy": 50,
            "unknown": 50,
        },
        "recall_at_5": 0.92,
        "recall_delta_vs_legacy_at_5": 0.0,
        "mrr_delta_vs_legacy_at_10": 0.0,
        "precision_delta_vs_legacy_at_5": 0.0,
        "conflict_retention_rate": 1.0,
        "unknown_abstention_rate": 1.0,
        "p99_latency_ms": 100.0,
        "legacy_p99_latency_ms": 100.0,
        "privacy_leak_count": 0,
        "boundary_tests_passed": True,
        "concurrent_read_count": 100,
        "concurrent_write_count": 10,
        "crash_injection_points_passed": 3,
        "rollback_data_basis": "REAL_PRIVATE_DATA_OFFLINE_COPY",
        "rollback_source_sha256": "a" * 64,
        "rollback_restored_sha256": "a" * 64,
        "rollback_lost_acknowledged_writes": 0,
        "rollback_duration_minutes": 4.5,
    }


def test_replacement_gate_requires_complete_evidence_and_real_data_rollback():
    assert evaluate_replacement_evidence(None)["status"] == "REVIEW_REQUIRED"
    evidence = _passing_replacement_metrics()
    result = evaluate_replacement_evidence(evidence)
    assert result["status"] == "METRICS_PASS_REVIEW_REQUIRED"
    assert result["evidence_authenticated"] is False

    evidence["rollback_data_basis"] = "SYNTHETIC_FIXTURE"
    result = evaluate_replacement_evidence(evidence)
    assert result["status"] == "FAIL"
    assert "rollback_not_tested_on_real_private_data_copy" in result["failed_gates"]


def test_replacement_gate_rejects_conflict_loss_leakage_and_slow_tail():
    evidence = _passing_replacement_metrics()
    evidence["conflict_retention_rate"] = 0.99
    evidence["privacy_leak_count"] = 1
    evidence["p99_latency_ms"] = 300.0
    result = evaluate_replacement_evidence(evidence)
    assert result["status"] == "FAIL"
    assert "conflict_retention_below_100_percent" in result["failed_gates"]
    assert "privacy_leak_detected" in result["failed_gates"]
    assert "p99_latency_gate_failed" in result["failed_gates"]
