from datetime import datetime, timezone

from core.meaning_line import CONTRACT_VERSION, validate_meaning_line_batch


NOW = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _candidate(**overrides):
    value = {
        "contract_version": CONTRACT_VERSION,
        "source_scope": "EXPLICIT_USER_INPUT",
        "source_refs": ["user_explicit_input:2026-09-01:0001"],
        "observed_at": "2026-09-01T00:00:00+00:00",
        "expires_at": "2026-09-02T00:00:00+00:00",
        "claim_class": "FACT",
        "claim_kind": "DIRECT_OBSERVATION",
        "claim": "The owner explicitly requested evidence-backed continuity work.",
        "counterexample_ref": "user_explicit_input:2026-09-01:0001",
        "candidate_envelope": {
            "semantic_key": "explicit-continuity-request-v1",
            "candidate_snapshot_hash": "a" * 64,
            "selection_reason": "explicit source, bounded scope, and a named counterexample reference",
            "sandbox_scope": "FREE_ZONE_ONLY",
            "review_status": "NEEDS_HUMAN_CONFIRMATION",
        },
    }
    value.update(overrides)
    return value


def _validate(items, **kwargs):
    return validate_meaning_line_batch(items, policy={"max_items": 2}, existing_candidates=[], now=NOW, **kwargs)


def test_valid_explicit_input_is_a_shadow_candidate_without_side_effects():
    result = _validate([_candidate()])
    assert result["verdict"] == "VALID_SHADOW_BATCH"
    assert result["shadow_batch"][0]["sandbox_scope"] == "FREE_ZONE_ONLY"
    assert result["shadow_batch"][0]["review_status"] == "NEEDS_HUMAN_CONFIRMATION"
    assert result["side_effects"] == {
        "persistent_write": False,
        "task_created": False,
        "model_called": False,
        "daemon_called": False,
        "external_action": False,
    }


def test_owner_interpretation_must_remain_a_hypothesis():
    item = _candidate(claim_kind="OWNER_INTERPRETATION", claim="This preference means the owner trusts autonomous financial decisions.")
    assert _validate([item])["reason_code"] == "REJECTED_OWNER_INTERPRETATION_NOT_HYPOTHESIS"
    item["claim_class"] = "HYPOTHESIS"
    assert _validate([item])["verdict"] == "VALID_SHADOW_BATCH"


def test_duplicate_expired_unbounded_and_forbidden_inputs_are_rejected():
    item = _candidate()
    duplicate = validate_meaning_line_batch(
        [item], policy={"max_items": 2}, existing_candidates=[{"semantic_key": "explicit-continuity-request-v1"}], now=NOW,
    )
    assert duplicate["reason_code"] == "REJECTED_DUPLICATE_SEMANTIC_KEY"
    assert _validate([_candidate(observed_at="2026-08-31T00:00:00+00:00", expires_at="2026-08-31T23:59:59+00:00")])["reason_code"] == "REJECTED_SOURCE_EXPIRED"
    assert validate_meaning_line_batch([item, _candidate()], policy={"max_items": 1}, existing_candidates=[], now=NOW)["reason_code"] == "REJECTED_BATCH_LIMIT"
    assert _validate([_candidate(raw_chat="private content")])["reason_code"] == "REJECTED_FORBIDDEN_FIELD"
    assert _validate([_candidate(task_id="must-not-dispatch")])["reason_code"] == "REJECTED_FORBIDDEN_FIELD"


def test_same_fixtures_have_the_same_result():
    first = _validate([_candidate()])
    second = _validate([_candidate()])
    assert first == second
