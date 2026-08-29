import json

import pytest

from core.free_zone_autonomy import FreeZoneAutonomy
from core.sandbox_society import SandboxSociety
from core.semantic_seed import SemanticSeedError, normalize_semantic_seed


def _seed(**overrides):
    value = {
        "food_kind": "semantic_seed",
        "contract_version": "ace.semantic_seed.v1",
        "source_ref": "https://example.invalid/article",
        "source_snapshot_hash": "a" * 64,
        "source_kind": "user_supplied_article",
        "extracted_mechanism": "Stable systems use shared contracts and visible feedback rather than repeated owner intervention.",
        "ace_symptom": "The owner has repeatedly needed to remind ACE to observe, consume, and review work.",
        "transfer_hypothesis": "Echoing unresolved validation context into the next eligible window may reduce reliance on reminders.",
        "counterexample_question": "Are the existing loops already sufficient but only invisible, rather than unconsumed?",
        "next_verification": "Trace one validator outcome through experience and later reuse using independent local evidence.",
        "local_evidence_refs": ["C:/tmp/claw-soul/lab_02/principles.md#Principle_022"],
        "external_evidence_refs": [],
        "lineage": ["user_observation", "semantic_seed"],
    }
    value.update(overrides)
    return value


def test_semantic_seed_is_pending_with_one_source_and_has_no_execution_authority():
    seed = normalize_semantic_seed(_seed())

    assert seed["status"] == "PENDING"
    assert seed["independent_evidence_status"] == "NOT_ASSESSED"
    assert seed["consumption_mode"] == "sandbox_report_only"
    assert seed["source_evidence_weight"] == "UNASSESSED"
    assert seed["production_integration"] is False
    assert seed["taskpool_authority"] is False
    assert seed["automatic_model_call"] is False
    assert seed["seed_hash"]


def test_semantic_seed_requires_complete_mechanism_and_verification_shape():
    with pytest.raises(SemanticSeedError, match="counterexample_question"):
        normalize_semantic_seed(_seed(counterexample_question=""))


def test_semantic_seed_requires_explicit_contract_and_sha256_snapshot_without_counting_refs_as_independence():
    without_contract = _seed()
    without_contract.pop("contract_version")
    with pytest.raises(SemanticSeedError, match="contract_version"):
        normalize_semantic_seed(without_contract)
    with pytest.raises(SemanticSeedError, match="source_snapshot_hash"):
        normalize_semantic_seed(_seed(source_snapshot_hash="not-a-sha256"))

    seed = normalize_semantic_seed(_seed(local_evidence_refs=["same://source", "same://source"], external_evidence_refs=[]))
    assert seed["independent_evidence_status"] == "NOT_ASSESSED"


def test_semantic_seed_inbox_becomes_pending_sandbox_evidence_not_a_task(tmp_path):
    root = tmp_path / "sandbox"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "article-seed.json").write_text(json.dumps(_seed()), encoding="utf-8")

    report = FreeZoneAutonomy(root, selection_seed_factory=lambda: 11).run_turn()

    assert report["claim"]["source_kind"] == "semantic_seed"
    assert report["execution"]["outcome"] == "INCONCLUSIVE"
    experiment = json.loads((root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    seed = experiment["metadata"]["semantic_seed"]
    assert seed["status"] == "PENDING"
    assert seed["extracted_mechanism"] == _seed()["extracted_mechanism"]
    assert experiment["evidence"]["requires_independent_evidence"] is True
    assert experiment["production_integration"] is False
    assert not (root / "task_pool").exists()
    assert not (root / "experience").exists()


def test_semantic_seed_distillation_preserves_reverse_audit_for_later_echo_only(tmp_path):
    root = tmp_path / "sandbox"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "article-seed.json").write_text(json.dumps(_seed()), encoding="utf-8")

    report = FreeZoneAutonomy(root, selection_seed_factory=lambda: 7).run_turn()
    society = SandboxSociety(root).run_turn()
    distillation = json.loads((root / "distillations" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))

    assert society["roles"]["curator"]["new_distillations"][0]["status"] == "OPEN_QUESTION"
    assert distillation["semantic_seed"]["ace_symptom"] == _seed()["ace_symptom"]
    assert distillation["semantic_seed"]["transfer_hypothesis"] == _seed()["transfer_hypothesis"]
    assert distillation["semantic_seed"]["next_verification"] == _seed()["next_verification"]
    assert distillation["automatic_task_creation"] is False
    assert distillation["production_integration"] is False


def test_incomplete_semantic_seed_is_preserved_as_pending_unstructured_observation_not_rejected(tmp_path):
    root = tmp_path / "sandbox"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "broken-seed.json").write_text(json.dumps(_seed(next_verification="")), encoding="utf-8")

    report = FreeZoneAutonomy(root).run_turn()

    assert report["claim"]["source_kind"] == "semantic_seed_unstructured"
    assert report["execution"]["outcome"] == "INCONCLUSIVE"
    experiment = json.loads((root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    assert experiment["evidence"]["status"] == "PENDING"
    assert experiment["evidence"]["normalization_error"] == "next_verification is required"
    assert experiment["evidence"]["payload_hash"]
    assert experiment["production_integration"] is False
    assert not (root / "task_pool").exists()


def test_untyped_inbox_behavior_remains_generic_and_non_promoting(tmp_path):
    root = tmp_path / "sandbox"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "generic.json").write_text(json.dumps({"question": "ordinary preserved input"}), encoding="utf-8")

    report = FreeZoneAutonomy(root).run_turn()
    assert report["claim"]["source_kind"] == "inbox"
    assert report["execution"]["outcome"] == "INCONCLUSIVE"
