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
    assert report["caller_unification"]["status"] == "NOT_MET"
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
    assert report["caller_unification"]["facade"] == "NOT_IMPLEMENTED"


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
