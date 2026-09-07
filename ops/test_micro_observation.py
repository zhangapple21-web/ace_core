import pytest

from core.micro_observation import build_micro_observation, validate_micro_observation


def test_builds_replayable_atomic_unit():
    value = build_micro_observation(
        observation="quote snapshot exists", intent="test a bounded strategy",
        constraints=["evaluation only"], action="record D0",
        result="journal entry", feedback="await D+7", next_question="does it hold?",
        evidence_refs=["snapshot:abc"],
    )
    assert value["contract_version"] == "ace.micro_observation.v1"
    assert value["production_integration"] is False


def test_rejects_missing_evidence_and_production_fields():
    with pytest.raises(ValueError, match="evidence_refs"):
        build_micro_observation(
            observation="o", intent="i", constraints=[], action="a", result="r",
            feedback="f", next_question="q", evidence_refs=[],
        )
    value = build_micro_observation(
        observation="o", intent="i", constraints=[], action="a", result="r",
        feedback="f", next_question="q", evidence_refs=["e"],
    )
    value["production_integration"] = True
    with pytest.raises(ValueError, match="production_integration"):
        validate_micro_observation(value)


def test_rejects_forbidden_outbound_fields():
    value = build_micro_observation(
        observation="o", intent="i", constraints=[], action="a", result="r",
        feedback="f", next_question="q", evidence_refs=["e"],
    )
    value["result"] = {"recommendation": "BUY"}
    with pytest.raises(ValueError, match="forbidden field"):
        validate_micro_observation(value)



