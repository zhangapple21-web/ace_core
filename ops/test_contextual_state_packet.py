import pytest

from core.contextual_state_packet import ContextualStatePacket


def _scene(*, new_fact=None):
    facts = [
        {
            "fact_id": "FACT-DOOR-CLOSED",
            "statement": "The door was closed before the conversation.",
            "observed_at": "2026-09-01T00:00:00Z",
            "entities": ["A", "B"],
            "scope": "scene-1",
            "evidence_refs": ["evidence/door-log.json"],
        },
        {
            "fact_id": "FACT-PROMISE",
            "statement": "A promised to meet B before dusk.",
            "observed_at": "2026-09-01T00:01:00Z",
            "entities": ["A", "B"],
            "scope": "scene-1",
            "evidence_refs": ["evidence/promise-note.md"],
        },
    ]
    if new_fact:
        facts.append(new_fact)
    return {
        "packet_id": "CSP-SCENE-ONE",
        "scope": "scene-1",
        "question": "Why does A avoid answering B?",
        "entities": ["A", "B"],
        "facts": facts,
        "relations": [
            {
                "relation_id": "REL-A-B",
                "subject": "A",
                "object": "B",
                "kind": "unkept_commitment",
                "state": "ACTIVE",
                "evidence_refs": ["evidence/promise-note.md"],
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "HYP-A-SHAME",
                "statement": "A avoids answering because A is ashamed of missing the promise.",
                "about_entities": ["A", "B"],
                "supported_by": ["FACT-PROMISE", "REL-A-B"],
                "falsified_by": ["FACT-A-COERCED"],
                "status": "ACTIVE",
            },
            {
                "hypothesis_id": "HYP-A-DECEPTION",
                "statement": "A avoids answering to conceal an unrelated deception.",
                "about_entities": ["A", "B"],
                "supported_by": ["FACT-DOOR-CLOSED"],
                "falsified_by": ["FACT-A-COERCED"],
                "status": "ACTIVE",
            },
        ],
        "constraints": ["research only", "do not treat hypotheses as facts"],
    }


def test_packet_keeps_facts_hypotheses_and_competing_interpretations_separate():
    packet = ContextualStatePacket().build(_scene())

    assert packet["scope"] == "FREE_ZONE_RESEARCH_ONLY"
    assert packet["production_integration"] is False
    assert packet["side_effects"] == {"task_created": False, "model_called": False, "production_runtime_mutation": False}
    assert [item["hypothesis_id"] for item in packet["active_hypotheses"]] == ["HYP-A-DECEPTION", "HYP-A-SHAME"]
    assert all(item["epistemic_status"] == "HYPOTHESIS" for item in packet["active_hypotheses"])
    assert all(item["epistemic_status"] == "FACT" for item in packet["relevant_facts"])
    assert packet["competing_hypothesis_groups"] == [["HYP-A-DECEPTION", "HYP-A-SHAME"]]


def test_new_falsifying_fact_retracts_only_the_hypotheses_that_name_it():
    packet = ContextualStatePacket().build(
        _scene(
            new_fact={
                "fact_id": "FACT-A-COERCED",
                "statement": "A was prevented from attending by an independently recorded emergency.",
                "observed_at": "2026-09-01T00:02:00Z",
                "entities": ["A"],
                "scope": "scene-1",
                "evidence_refs": ["evidence/emergency-log.json"],
            }
        )
    )

    assert packet["active_hypotheses"] == []
    assert {item["hypothesis_id"] for item in packet["retracted_hypotheses"]} == {"HYP-A-SHAME", "HYP-A-DECEPTION"}
    assert all(item["retraction_reason"] == "falsifying_fact_present" for item in packet["retracted_hypotheses"])


def test_packet_rejects_hypotheses_that_smuggle_unknown_support_as_fact():
    scene = _scene()
    scene["hypotheses"][0]["supported_by"] = ["FACT-NOT-IN-PACKET"]

    with pytest.raises(ValueError, match="unknown support reference"):
        ContextualStatePacket().build(scene)


def test_packet_requires_future_falsifiers_to_remain_explicit_fact_identities():
    scene = _scene()
    scene["hypotheses"][0]["falsified_by"] = ["a feeling changed"]

    with pytest.raises(ValueError, match="FACT-\\* identities"):
        ContextualStatePacket().build(scene)


def test_packet_is_deterministic_except_for_the_declared_packet_identity():
    builder = ContextualStatePacket()
    first = builder.build(_scene())
    second = builder.build(_scene())

    assert first == second
    assert len(first["packet_hash"]) == 64
