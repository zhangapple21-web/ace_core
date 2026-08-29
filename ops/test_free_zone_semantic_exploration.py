import copy
import hashlib
import json

from core.free_zone_semantic_exploration import SemanticSliceExplorer


def _candidates():
    return [
        {
            "fingerprint": "distillation:COUNTEREXAMPLE_ONLY:EXP-FAIL",
            "source_kind": "distillation",
            "source_ref": "sandbox/distillations/EXP-FAIL.json",
            "parent_status": "COUNTEREXAMPLE_ONLY",
        },
        {
            "fingerprint": "distillation:OPEN_QUESTION:EXP-OPEN",
            "source_kind": "distillation",
            "source_ref": "sandbox/distillations/EXP-OPEN.json",
            "parent_status": "OPEN_QUESTION",
        },
        {
            "fingerprint": "inbox:QUESTION-ONE",
            "source_kind": "inbox",
            "source_ref": "sandbox/inbox/question.json",
        },
    ]


def _lazy_cat_challenge(fingerprint, missing_dimensions):
    challenge = {
        "contract_version": "ace.lazy_cat_audit.v1",
        "challenge_id": fingerprint,
        "missing_dimensions": missing_dimensions,
        "question": "This free text is intentionally not part of the semantic slice.",
    }
    challenge["challenge_hash"] = hashlib.sha256(
        json.dumps(challenge, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "fingerprint": fingerprint,
        "source_kind": "lazy_cat_challenge",
        "source_ref": f"sandbox/lazy_cat/challenges/{fingerprint}.json",
        "challenge": challenge,
    }


def test_semantic_slice_is_descriptive_and_never_an_outcome_or_production_score():
    counterexample = SemanticSliceExplorer.describe(_candidates()[0])

    assert counterexample["dimensions"]["epistemic_shape"] == "counterexample_reobservation"
    assert counterexample["dimensions"]["execution_stance"] == "DIRECT_OBSERVATION"
    assert counterexample["descriptive_only"] is True
    assert counterexample["outcome_used"] is False
    assert counterexample["quality_score_used"] is False
    assert counterexample["production_value_used"] is False
    assert "profit" not in counterexample["slice_id"].lower()


def test_seeded_semantic_allocation_replays_from_the_same_snapshot_and_state():
    first_state = {}
    second_state = {}
    first = SemanticSliceExplorer.allocate(copy.deepcopy(_candidates()), limit=3, state=first_state, selection_seed=741)
    second = SemanticSliceExplorer.allocate(copy.deepcopy(_candidates()), limit=3, state=second_state, selection_seed=741)

    assert [item["fingerprint"] for item in first["selected"]] == [item["fingerprint"] for item in second["selected"]]
    assert first["resource_selection"] == second["resource_selection"]
    assert first["resource_selection"]["candidate_snapshot_sha256"]
    assert first["resource_selection"]["selection_seed"] == 741
    assert first_state["semantic_exploration"]["slice_draw_counts"] == second_state["semantic_exploration"]["slice_draw_counts"]


def test_underrepresented_slices_have_higher_probability_but_no_slice_is_rejected():
    state = {
        "semantic_exploration": {
            "slice_draw_counts": {
                SemanticSliceExplorer.describe(_candidates()[0])["slice_id"]: 11,
                SemanticSliceExplorer.describe(_candidates()[1])["slice_id"]: 0,
            },
        },
    }
    result = SemanticSliceExplorer.allocate(copy.deepcopy(_candidates()), limit=1, state=state, selection_seed=19)
    draw = result["resource_selection"]["draws"][0]
    probabilities = {item["slice_id"]: item["probability"] for item in draw["slice_weights"]}
    counter_slice = SemanticSliceExplorer.describe(_candidates()[0])["slice_id"]
    open_slice = SemanticSliceExplorer.describe(_candidates()[1])["slice_id"]

    assert probabilities[open_slice] > probabilities[counter_slice] > 0
    assert draw["selection_reason"] == "SOURCE_FAIR_ROUND_ROBIN_THEN_UNDERREPRESENTED_SEMANTIC_SLICE_DRAW"
    assert result["resource_selection"]["quality_decision_performed"] is False
    assert result["resource_selection"]["outcome_used"] is False
    assert result["resource_selection"]["production_value_used"] is False


def test_lazy_cat_challenges_split_only_by_their_declared_structural_gaps():
    dissent_only = _lazy_cat_challenge("CHALLENGE-DISSENT", ["dissent_blueprint"])
    boundary_and_dissent = _lazy_cat_challenge(
        "CHALLENGE-BOUNDARY-DISSENT",
        ["boundary_intact", "dissent_blueprint"],
    )
    same_gaps_different_order = _lazy_cat_challenge(
        "CHALLENGE-DISSENT-BOUNDARY",
        ["dissent_blueprint", "boundary_intact"],
    )

    dissent_slice = SemanticSliceExplorer.describe(dissent_only)
    combined_slice = SemanticSliceExplorer.describe(boundary_and_dissent)
    reordered_slice = SemanticSliceExplorer.describe(same_gaps_different_order)

    assert dissent_slice["dimensions"]["challenge_gap_signature"] == "dissent_blueprint"
    assert combined_slice["dimensions"]["challenge_gap_signature"] == "boundary_intact+dissent_blueprint"
    assert dissent_slice["slice_id"] != combined_slice["slice_id"]
    assert combined_slice["slice_id"] == reordered_slice["slice_id"]
    assert combined_slice["slice_basis"] == [
        "candidate.source_kind",
        "candidate.challenge.missing_dimensions",
    ]
    assert "question" not in combined_slice["slice_id"]
    assert combined_slice["outcome_used"] is False
    assert combined_slice["quality_score_used"] is False
    assert combined_slice["production_value_used"] is False


def test_challenge_gap_slices_have_positive_probability_and_replay_without_mutating_the_challenge():
    candidates = [
        _lazy_cat_challenge("CHALLENGE-DISSENT", ["dissent_blueprint"]),
        _lazy_cat_challenge("CHALLENGE-LINEAGE", ["lineage"]),
    ]
    original = copy.deepcopy(candidates)
    first = SemanticSliceExplorer.allocate(candidates, limit=2, state={}, selection_seed=503)
    second = SemanticSliceExplorer.allocate(copy.deepcopy(original), limit=2, state={}, selection_seed=503)

    assert candidates == original
    assert [item["fingerprint"] for item in first["selected"]] == [
        item["fingerprint"] for item in second["selected"]
    ]
    assert first["resource_selection"] == second["resource_selection"]
    assert first["resource_selection"]["semantic_slice_count"] == 2
    snapshot_hashes = {
        item["fingerprint"]: item["source_record_hash"]
        for item in first["resource_selection"]["candidate_snapshot"]
    }
    for candidate in original:
        unsigned = {key: value for key, value in candidate["challenge"].items() if key != "challenge_hash"}
        expected = hashlib.sha256(
            json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert candidate["challenge"]["challenge_hash"] == expected
        assert snapshot_hashes[candidate["fingerprint"]] == expected
    first_draw = first["resource_selection"]["draws"][0]
    assert len(first_draw["slice_weights"]) == 2
    assert all(item["probability"] > 0 for item in first_draw["slice_weights"])
