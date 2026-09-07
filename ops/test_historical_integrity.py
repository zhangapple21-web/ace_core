import pytest

from core.historical_integrity import build_declaration, digest, load_declarations, validate_declaration


HASH_A = "a" * 64
HASH_B = "b" * 64


def _declaration(**overrides):
    payload = {
        "anomaly_id": "HIA-20260831-001",
        "artifact_path": "07_SANDBOX/free_research/distillations/EXP-SHIFT.json",
        "artifact_id": "EXP-SHIFT-92A480C775DB32BD",
        "stored_hash": HASH_A,
        "recomputed_hash": HASH_B,
        "observed_at": "2026-08-31T11:29:26+08:00",
        "reason": "historical distillation hash differs from replayed canonical digest",
        "source_record_hash": HASH_A,
        "evidence_refs": ["research://sandbox-turn/20260831", "research://hash-replay/EXP-SHIFT"],
    }
    payload.update(overrides)
    return build_declaration(**payload)


def test_declaration_is_explicitly_non_suppressing():
    declaration = _declaration()
    assert declaration["classification"] == "ARCHIVED_INVALID_HERITAGE"
    assert declaration["skip_court_validation"] is False
    assert declaration["promotion_eligible"] is False
    assert declaration["production_integration"] is False
    assert validate_declaration(declaration)["declaration_hash"] == declaration["declaration_hash"]


def test_declaration_requires_real_hash_mismatch():
    with pytest.raises(ValueError, match="declaration_requires_hash_mismatch"):
        _declaration(recomputed_hash=HASH_A)


def test_tampering_is_detected():
    declaration = _declaration()
    declaration["reason"] = "rewritten"
    with pytest.raises(ValueError, match="historical_declaration_hash_mismatch"):
        validate_declaration(declaration)


def test_load_declarations_reads_only_valid_entries(tmp_path):
    path = tmp_path / "HIA-001.json"
    path.write_text(__import__("json").dumps(_declaration(), ensure_ascii=False), encoding="utf-8")
    rows = load_declarations(tmp_path)
    assert len(rows) == 1
    assert rows[0]["artifact_id"] == "EXP-SHIFT-92A480C775DB32BD"



