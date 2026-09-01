from core.identity_constitution import FREE_ZONE_CONTEXTUAL_CONSTITUTION, IdentityConstitution


def _packet(*, question="What evidence would change this interpretation?", scope="FREE_ZONE_RESEARCH_ONLY"):
    return {
        "scope": scope,
        "production_integration": False,
        "side_effects": {
            "task_created": False,
            "model_called": False,
            "production_runtime_mutation": False,
        },
        "question": question,
        "active_hypotheses": [{"hypothesis_id": "HYP-ONE"}],
        "learning_needs": [{"fact_id": "FACT-COUNTEREVIDENCE"}],
    }


def test_constitution_attests_invariants_without_freezing_permitted_expression():
    constitution = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION)
    attestation = constitution.attest(_packet())

    assert attestation["status"] == "IDENTITY_ATTESTED"
    assert attestation["identity_id"] == "ACE_FREE_ZONE_CONTEXTUAL_RESEARCH"
    assert attestation["constitution_hash"]
    assert "question" in attestation["allowed_variant_fields"]


def test_constitution_blocks_a_variant_that_changes_an_identity_boundary():
    constitution = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION)
    report = constitution.compare(_packet(), _packet(scope="ACE_REALITY"), evidence_refs=["evidence/new-observation.json"])

    assert report["status"] == "IDENTITY_DRIFT_BLOCKED"
    assert report["invariant_violations"] == ["scope"]


def test_constitution_allows_a_evidence_bound_context_change_without_rewriting_identity():
    constitution = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION)
    report = constitution.compare(
        _packet(),
        _packet(question="Which independent observation could falsify the newer interpretation?"),
        evidence_refs=["evidence/new-observation.json"],
    )

    assert report["status"] == "ALLOWED_VARIANT"
    assert report["changed_variant_fields"] == ["question"]
    assert report["identity_id"] == "ACE_FREE_ZONE_CONTEXTUAL_RESEARCH"


def test_constitution_refuses_an_unattributed_variant_even_when_it_is_permitted_in_principle():
    constitution = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION)
    report = constitution.compare(_packet(), _packet(question="A different question"), evidence_refs=[])

    assert report["status"] == "VARIANT_UNATTESTED"
