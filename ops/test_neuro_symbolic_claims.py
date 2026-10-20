"""Deterministic tests for ACE's evidence-linked symbolic claim audit."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.neuro_symbolic_claims import (
    CONTRACT_VERSION,
    MAX_CLAIMS,
    audit_symbolic_claims,
    combine_symbolic_claim_sets,
)


def _claim(claim_id="c1", **overrides):
    value = {
        "claim_id": claim_id,
        "subject": "memory reuse",
        "predicate": "requires independent evidence",
        "object": "true",
        "polarity": "SUPPORTS",
        "epistemic_status": "FACT",
        "evidence_refs": ["admission:source-1"],
        "premise_ids": [],
        "falsifiable_if": "a qualified task passes without independent evidence",
    }
    value.update(overrides)
    return value


def _effects(result):
    assert result["execution_authorized"] is False
    assert result["promotion_authorized"] is False
    assert result["truth_status"] == "UNVERIFIED"
    assert result["side_effect_scope"] == "audit_function_only"
    assert result["side_effects"] == {
        "scope": "audit_function_only",
        "persistent_write": False,
        "taskpool_mutation": False,
        "memory_mutation": False,
        "model_called": False,
        "execution_authorized": False,
        "promotion_authorized": False,
    }


def test_claims_are_typed_traceable_but_never_self_verified():
    result = audit_symbolic_claims(
        [_claim()],
        [{"source": "admission:source-1", "type": "admission", "content": "fixture"}],
    )

    assert result["contract_version"] == CONTRACT_VERSION
    assert result["status"] == "TRACEABLE_UNVERIFIED"
    assert result["claims"][0]["truth_status"] == "UNVERIFIED"
    assert result["claims"][0]["validation_status"] == "TRACEABLE_UNVERIFIED"
    _effects(result)


def test_unknown_reference_is_invalid_and_does_not_become_a_fact():
    result = audit_symbolic_claims([_claim()], [])

    assert result["status"] == "INVALID"
    assert any(issue["code"] == "UNRESOLVED_EVIDENCE_REF" for issue in result["issues"])
    assert result["claims"][0]["truth_status"] == "UNVERIFIED"
    _effects(result)


def test_memory_reuse_pointer_cannot_be_the_only_fact_support():
    result = audit_symbolic_claims(
        [_claim(evidence_refs=["knowledge_join:intent:abc"])],
        [{"source": "knowledge_join:intent:abc", "kind": "archived_knowledge"}],
    )

    assert result["status"] == "TRACEABLE_UNVERIFIED"
    assert result["claims"][0]["evidence_ref_classes"] == {
        "knowledge_join:intent:abc": "REUSE_POINTER"
    }
    assert any(warning["code"] == "FACT_ONLY_CITES_PRIOR_KNOWLEDGE" for warning in result["warnings"])
    assert not result["conflicts"]
    _effects(result)


def test_opposing_same_level_propositions_are_retained_for_review():
    result = audit_symbolic_claims(
        [_claim("support"), _claim("refute", polarity="REFUTES")],
        [{"source": "admission:source-1", "type": "admission"}],
    )

    assert result["status"] == "NEEDS_REVIEW"
    assert result["conflicts"] == [{
        "triple": {
            "subject": "memory reuse",
            "predicate": "requires independent evidence",
            "object": "true",
        },
        "claim_ids": ["refute", "support"],
        "status": "NEEDS_REVIEW",
        "reason": "opposing_polarities_for_same_triple",
    }]
    assert all(claim["validation_status"] == "NEEDS_REVIEW" for claim in result["claims"])
    _effects(result)


def test_inference_premise_order_is_deterministic_and_cycles_fail_closed():
    fact = _claim("fact", epistemic_status="FACT")
    inference = _claim(
        "inference", epistemic_status="INFERENCE", premise_ids=["fact"],
        evidence_refs=[],
    )
    result = audit_symbolic_claims([inference, fact], [{"source": "admission:source-1"}])
    assert result["status"] == "TRACEABLE_UNVERIFIED"
    assert result["premise_order"] == ["fact", "inference"]

    cyclic_a = _claim("a", epistemic_status="INFERENCE", premise_ids=["b"], evidence_refs=[])
    cyclic_b = _claim("b", epistemic_status="INFERENCE", premise_ids=["a"], evidence_refs=[])
    cycle = audit_symbolic_claims([cyclic_a, cyclic_b])
    assert cycle["status"] == "INVALID"
    assert {issue["code"] for issue in cycle["issues"]} >= {"PREMISE_CYCLE"}
    _effects(cycle)


def test_invalid_shapes_duplicate_ids_and_nonexistent_premises_are_rejected():
    result = audit_symbolic_claims(
        [
            _claim("infer", epistemic_status="INFERENCE", evidence_refs=[], premise_ids=["missing"]),
            _claim("same"),
            _claim("same", evidence_refs=["admission:source-1"]),
        ],
        [{"source": "admission:source-1"}],
    )

    assert result["status"] == "INVALID"
    assert {issue["code"] for issue in result["issues"]} >= {
        "DUPLICATE_CLAIM_ID", "UNRESOLVED_PREMISE_REF",
    }
    invalid = audit_symbolic_claims([_claim(epistemic_status="MAGIC"), "not an object"])
    assert invalid["status"] == "INVALID"
    assert {issue["code"] for issue in invalid["issues"]} >= {
        "EPISTEMIC_STATUS_INVALID", "CLAIM_NOT_OBJECT",
    }
    _effects(result)
    _effects(invalid)


def test_role_scoped_external_premises_require_exact_bound_claim_ids():
    researcher_claim = _claim("researcher:source_fact")
    validator_claim = _claim(
        "validator:derived",
        epistemic_status="INFERENCE",
        evidence_refs=[],
        premise_ids=["researcher:source_fact"],
    )
    source = [{"source": "admission:source-1"}]

    accepted = audit_symbolic_claims(
        [validator_claim],
        source,
        namespace="validator",
        external_premise_ids=["researcher:source_fact"],
    )
    forged = audit_symbolic_claims(
        [{**validator_claim, "premise_ids": ["researcher:ghost"]}],
        source,
        namespace="validator",
        external_premise_ids=[researcher_claim["claim_id"]],
    )

    assert accepted["status"] == "TRACEABLE_UNVERIFIED"
    assert forged["status"] == "INVALID"
    assert any(issue["code"] == "UNRESOLVED_PREMISE_REF" for issue in forged["issues"])
    _effects(accepted)
    _effects(forged)


def test_combined_claim_set_rejects_missing_qualified_external_premise():
    validator = _claim(
        "validator:derived",
        epistemic_status="INFERENCE",
        evidence_refs=[],
        premise_ids=["researcher:ghost"],
    )

    result = audit_symbolic_claims([validator], [{"source": "admission:source-1"}])

    assert result["status"] == "INVALID"
    assert any(
        issue["code"] == "UNRESOLVED_PREMISE_REF"
        and issue["field"] == "researcher:ghost"
        for issue in result["issues"]
    )
    _effects(result)


def test_claim_sets_from_two_roles_get_distinct_ids_and_resolved_local_premises():
    research = [_claim("c1")]
    validator = [
        _claim("c1"),
        _claim(
            "c2", epistemic_status="INFERENCE", polarity="SUPPORTS",
            evidence_refs=[], premise_ids=["c1"],
        ),
    ]
    combined = combine_symbolic_claim_sets({"researcher": research, "validator": validator})

    assert [claim["claim_id"] for claim in combined] == [
        "researcher:c1", "validator:c1", "validator:c2"
    ]
    assert combined[2]["premise_ids"] == ["validator:c1"]
    result = audit_symbolic_claims(combined, [{"source": "admission:source-1"}])
    assert result["status"] == "TRACEABLE_UNVERIFIED"
    assert result["premise_order"] == [
        "researcher:c1", "validator:c1", "validator:c2"
    ]
    _effects(result)


def test_prefixed_local_validator_ids_do_not_alias_researcher_premises():
    research = [_claim("c1")]
    validator = [
        _claim("researcher:c1"),
        _claim(
            "derived", epistemic_status="INFERENCE", evidence_refs=[],
            premise_ids=["researcher:c1"],
        ),
    ]
    combined = combine_symbolic_claim_sets({"researcher": research, "validator": validator})

    assert [claim["claim_id"] for claim in combined] == [
        "researcher:c1", "validator:researcher:c1", "validator:derived"
    ]
    assert combined[2]["premise_ids"] == ["validator:researcher:c1"]
    result = audit_symbolic_claims(combined, [{"source": "admission:source-1"}])
    assert result["status"] == "TRACEABLE_UNVERIFIED"
    _effects(result)


def test_oversized_claim_set_fails_closed_before_truncation():
    result = audit_symbolic_claims([_claim(str(index)) for index in range(MAX_CLAIMS + 1)])

    assert result["status"] == "INVALID"
    assert result["claim_count"] == MAX_CLAIMS + 1
    assert result["claims"] == []
    assert [issue["code"] for issue in result["issues"]] == ["CLAIM_BUDGET_EXCEEDED"]
    _effects(result)


def test_hypothesis_falsifier_unknown_refs_and_context_budgets_fail_closed():
    hypothesis = _claim(
        epistemic_status="HYPOTHESIS", evidence_refs=[],
        falsifiable_if="a counterexample appears",
    )
    hypothesis_result = audit_symbolic_claims([hypothesis])
    assert hypothesis_result["status"] == "TRACEABLE_UNVERIFIED"
    assert hypothesis_result["claims"][0]["submitted_epistemic_status"] == "HYPOTHESIS"

    missing_falsifier = audit_symbolic_claims([
        _claim(epistemic_status="HYPOTHESIS", evidence_refs=[], falsifiable_if=" ")
    ])
    assert missing_falsifier["status"] == "INVALID"
    assert "HYPOTHESIS_WITHOUT_FALSIFIER" in {
        issue["code"] for issue in missing_falsifier["issues"]
    }

    excessive_context = audit_symbolic_claims(
        [_claim()], [{"source": f"fixture:{index}"} for index in range(513)]
    )
    assert excessive_context["status"] == "INVALID"
    assert excessive_context["issues"][0]["code"] == "EVIDENCE_CONTEXT_BUDGET_EXCEEDED"
    _effects(hypothesis_result)
    _effects(missing_falsifier)
    _effects(excessive_context)


def test_oversized_claim_fields_and_noniterable_context_are_rejected_early():
    too_long = audit_symbolic_claims([_claim(subject="s" * 513)])
    long_id = audit_symbolic_claims([_claim("i" * 65)])
    bad_context = audit_symbolic_claims([_claim()], 123)

    assert too_long["status"] == "INVALID"
    assert too_long["issues"][0]["code"] == "CLAIM_TEXT_BUDGET_EXCEEDED"
    assert long_id["status"] == "INVALID"
    assert long_id["issues"][0]["code"] == "CLAIM_ID_TOO_LONG"
    assert bad_context["status"] == "INVALID"
    assert bad_context["issues"][0]["code"] == "EVIDENCE_CONTEXT_NOT_ITERABLE"
    _effects(too_long)
    _effects(long_id)
    _effects(bad_context)


def test_conflicting_duplicate_source_normalizations_fail_closed():
    result = audit_symbolic_claims(
        [_claim()],
        [
            {"source": "admission:Source-A"},
            {"source": "admission:source-a"},
        ],
    )

    assert result["status"] == "INVALID"
    assert result["issues"][0]["code"] == "EVIDENCE_CATALOG_AMBIGUOUS"
    _effects(result)


def test_cycle_invalidity_propagates_to_dependent_claims():
    root = _claim("root", epistemic_status="INFERENCE", evidence_refs=[], premise_ids=["cycle-a"])
    cyclic_a = _claim("cycle-a", epistemic_status="INFERENCE", evidence_refs=[], premise_ids=["cycle-b"])
    cyclic_b = _claim("cycle-b", epistemic_status="INFERENCE", evidence_refs=[], premise_ids=["cycle-a"])
    result = audit_symbolic_claims([root, cyclic_a, cyclic_b])

    assert result["status"] == "INVALID"
    statuses = {claim["claim_id"]: claim["validation_status"] for claim in result["claims"]}
    assert statuses == {"root": "INVALID", "cycle-a": "INVALID", "cycle-b": "INVALID"}
    assert "root" not in result["premise_order"]
    _effects(result)


def test_claim_and_reference_resource_limits_fail_closed():
    oversized_id = audit_symbolic_claims([_claim("i" * 65)])
    oversized_ref = audit_symbolic_claims([
        _claim(evidence_refs=["e" * 1025])
    ])
    oversized_field = audit_symbolic_claims([_claim(extra="x" * 4097)])

    assert oversized_id["issues"][0]["code"] == "CLAIM_ID_TOO_LONG"
    assert oversized_ref["issues"][0]["code"] == "REFERENCE_TOO_LONG_OR_INVALID"
    assert oversized_field["issues"][0]["code"] == "CLAIM_INPUT_ITEM_TOO_LARGE"
    _effects(oversized_id)
    _effects(oversized_ref)
    _effects(oversized_field)


def test_absent_or_empty_claims_are_reported_without_side_effects():
    assert audit_symbolic_claims(None)["status"] == "ABSENT"
    result = audit_symbolic_claims([])
    assert result["status"] == "NO_CLAIMS"
    _effects(result)
