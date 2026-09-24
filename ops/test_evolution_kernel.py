import json

from core.evolution_kernel import (
    append_packets,
    assess_promotion,
    ingest_video_run,
    make_packet,
    route_learning,
)


def test_internal_failure_wins_over_external_inspiration():
    result = route_learning([
        {"candidate_id": "ext", "source_kind": "external_primary", "observation": {"evidence": ["r"]}},
        {"candidate_id": "local", "source_kind": "internal_failure", "observation": {"evidence": ["f"]}},
    ])
    assert result["selected"]["candidate_id"] == "local"
    assert result["reason"] == "internal_evidence_first"


def test_promotion_requires_painful_review_and_measurable_gain():
    base = {"baseline": {"failure_rate": 0.18}, "change": "retry gate", "test": {"passed": True}, "evaluation": {"failure_rate": 0.09}, "comparison": "improved", "measurable_gain": True}
    assert assess_promotion(base)["status"] == "REJECTED_MISSING_PAINFUL_REVIEW"
    base["painful_review"] = {
        "cost": "two failed render attempts",
        "counterfactual": "wrong shot would have entered the cut",
        "recurrence_risk": "medium",
        "reusable_lesson": "validate provider receipt before retry",
    }
    assert assess_promotion(base)["status"] == "PROMOTE"


def test_regression_always_requires_rollback():
    assert assess_promotion({
        "baseline": {"quality": 0.8}, "change": "new route", "test": {"passed": True},
        "evaluation": {"regression": True}, "comparison": "worse",
        "painful_review": {"cost": "", "counterfactual": "", "recurrence_risk": "", "reusable_lesson": ""},
        "measurable_gain": True,
    })["status"] == "ROLLBACK_REQUIRED"


def test_string_false_cannot_grant_promotion():
    result = assess_promotion({
        "baseline": {"quality": 0.8}, "change": "new route", "test": {"passed": "false"},
        "evaluation": {"measurable_gain": "false"}, "comparison": "same",
        "painful_review": {"cost": "c", "counterfactual": "cf", "recurrence_risk": "r", "reusable_lesson": "l"},
        "measurable_gain": "false",
    })
    assert result["status"] == "ROLLBACK_REQUIRED"


def test_video_receipt_ingestion_is_idempotent(tmp_path):
    run = tmp_path / "EL-test.json"
    run.write_text(json.dumps({
        "schema": "video_kingdom.external_learning_run.v1",
        "run_id": "EL-test",
        "source_boundary": "PUBLIC_PRIMARY_SOURCES_ONLY",
        "promotion": {"status": "NONE"},
        "records": [{"source_id": "pyscenedetect", "status": "NEW_OR_CHANGED", "readme_sha256": "abc", "readme_url": "https://example/readme"}],
    }), encoding="utf-8")
    packets = ingest_video_run(run)
    assert packets[0]["scope"] == "video"
    out = tmp_path / "bridge.jsonl"
    assert append_packets(packets, out)["added"] == 1
    assert append_packets(packets, out)["added"] == 0


def test_video_receipt_with_production_authority_is_rejected(tmp_path):
    run = tmp_path / "unsafe.json"
    run.write_text(json.dumps({
        "schema": "video_kingdom.external_learning_run.v1",
        "source_boundary": "PUBLIC_PRIMARY_SOURCES_ONLY",
        "promotion": {"status": "NONE"},
        "records": [{"source_id": "x", "status": "NEW_OR_CHANGED", "production_authority": "PROVIDER"}],
    }), encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="production_authority"):
        ingest_video_run(run)


def test_unchanged_video_receipt_creates_no_packet(tmp_path):
    run = tmp_path / "unchanged.json"
    run.write_text(json.dumps({
        "schema": "video_kingdom.external_learning_run.v1",
        "source_boundary": "PUBLIC_PRIMARY_SOURCES_ONLY",
        "promotion": {"status": "NONE"},
        "records": [{"source_id": "x", "status": "UNCHANGED", "source_content_key": "x:old"}],
    }), encoding="utf-8")
    assert ingest_video_run(run) == []


def test_same_source_content_key_is_deduplicated_across_runs(tmp_path):
    packet = make_packet(scope="video", candidate={"candidate_id": "run-1", "title": "x", "source_kind": "video_receipt", "source_content_key": "x:v1"})
    packet2 = make_packet(scope="video", candidate={"candidate_id": "run-2", "title": "x", "source_kind": "video_receipt", "source_content_key": "x:v1"})
    out = tmp_path / "bridge.jsonl"
    assert append_packets([packet], out)["added"] == 1
    assert append_packets([packet2], out)["added"] == 0


def test_packet_never_grants_execution():
    packet = make_packet(scope="video", candidate={"candidate_id": "x", "title": "x", "source_kind": "video_receipt"})
    assert packet["execution_authorized"] is False
    assert packet["production_integration"] is False
