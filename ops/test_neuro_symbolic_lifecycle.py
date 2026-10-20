"""Lifecycle integration tests for evidence-linked neuro-symbolic audits."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task_roles import Researcher, Validator
from ops.test_support import FixtureTaskPool
from ops.test_task_roles_contracts import _admission, _response, _Router


def _task_with_research(tmp_path, validator_response):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    source = "test:lifecycle-evidence"
    research_claim = {
        "claim_id": "shared",
        "subject": "source record",
        "predicate": "has label",
        "object": "alpha",
        "polarity": "SUPPORTS",
        "epistemic_status": "FACT",
        "evidence_refs": [source],
        "premise_ids": [],
        "falsifiable_if": "the record does not contain label alpha",
    }
    research_payload = {
        "facts": ["A fixture source record is admitted."],
        "evidence": ["The source identifier exists in task admission."],
        "inference": ["This audit establishes traceability only."],
        "unknowns": ["Whether the source semantically entails the claim."],
        "objections": ["No external source is used in this fixture."],
        "next_verification": "Check the source content independently.",
        "stop_condition": "Do not call traceability verified truth.",
        "symbolic_claims": [{**research_claim, "claim_id": "source_fact"}],
    }
    task = pool.create_task(
        "neuro symbolic lifecycle",
        hypothesis="A typed proposition can be audited without promotion.",
        creator="test",
        priority="high",
        tags=["task_type:reasoning"],
        admission={
            **_admission(source),
            "evidence": [{"source_ref": source, "content": "Fixture: record label alpha."}],
        },
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    research_router = _Router(_response(content=json.dumps(research_payload)))
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None
    Researcher(pool, llm_router=research_router).research_task(claimed)
    stored = pool.load_task(task.task_id)
    assert stored is not None and stored.status == "review"

    payload = {
        "facts": ["The local fixture is reviewable."],
        "evidence": ["Three independent evidence fixtures are attached."],
        "inference": ["The typed claim is only a validation candidate."],
        "unknowns": ["External truth is not tested."],
        "objections": ["The source is a test fixture."],
        "next_verification": "Keep the existing governed decision path.",
        "stop_condition": "No promotion follows from symbolic status.",
        "hard_objections": [],
        "advisory_objections": [],
        "counter_examples": [],
        "symbolic_claims": [{
            "claim_id": "source_fact",
            "subject": "source record",
            "predicate": "has label",
            "object": "alpha",
            "polarity": "SUPPORTS",
            "epistemic_status": "FACT",
            "evidence_refs": [source],
            "premise_ids": [],
            "falsifiable_if": "the record does not contain label alpha",
        }, {
            "claim_id": "shared",
            "subject": "source record",
            "predicate": "has label",
            "object": "alpha",
            "polarity": "SUPPORTS",
            "epistemic_status": "INFERENCE",
            "evidence_refs": [],
            "premise_ids": ["researcher:source_fact"],
            "falsifiable_if": "the task evidence fails to mention label alpha",
        }],
    }
    if validator_response is not None:
        payload.update(validator_response)
    router = _Router(_response(content=json.dumps(payload)))
    stored.evidence.extend([
        {"source": "test:independent-a", "content": "Independent fixture record A. " * 3},
        {"source": "test:independent-b", "content": "Independent fixture record B. " * 3},
        {"source": "test:independent-c", "content": "Independent fixture record C. " * 3},
    ])
    assert pool.update_task(stored)
    assert pool.move_task(task.task_id, "review", actor="researcher", task=stored) is not None
    return pool, task.task_id, router


def test_researcher_and_validator_claim_ids_are_namespaced_and_bound(tmp_path):
    pool, task_id, router = _task_with_research(tmp_path, None)

    result = Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    stored = pool.load_task(task_id)

    assert router.calls == 1
    assert stored is not None
    assert "validator_neuro_symbolic_audit" in stored.outputs
    combined = stored.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert combined["status"] == "TRACEABLE_UNVERIFIED"
    assert [claim["claim_id"] for claim in combined["claims"]] == [
        "researcher:source_fact", "validator:source_fact", "validator:shared"
    ]
    assert set(combined["premise_order"]) == {
        "researcher:source_fact", "validator:source_fact", "validator:shared"
    }
    assert combined["premise_order"].index("researcher:source_fact") < combined[
        "premise_order"
    ].index("validator:shared")
    assert combined["role_audits"]["researcher"]["binding_valid"] is True
    assert combined["role_audits"]["validator"]["binding_valid"] is True
    assert result["passed"] is True
    assert combined["execution_authorized"] is False
    assert combined["promotion_authorized"] is False


def test_research_audit_binding_survives_persisted_validator_shadow(tmp_path, monkeypatch):
    pool, task_id, router = _task_with_research(tmp_path, None)

    # Remove the disabled metadata keys entirely to represent legacy state: an
    # absent symbolic Validator result must not invalidate the Researcher proof.
    legacy_state = pool.load_task(task_id)
    assert legacy_state is not None
    for key in (
        "validator_neuro_symbolic_audit",
        "validator_neuro_symbolic_audit_task_id",
        "validator_neuro_symbolic_audit_model_sha256",
    ):
        legacy_state.outputs.pop(key, None)
    assert pool.update_task(legacy_state)

    first = Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    after_first = pool.load_task(task_id)
    assert after_first is not None
    assert after_first.outputs["validator_neuro_symbolic_audit_task_id"] == task_id
    assert after_first.outputs["neuro_symbolic_audit_task_id"] == task_id
    assert first["passed"] is True

    import core.task_roles as task_roles

    def accepted_cached_validator_response(task, _role, _router, _prompt, **_kwargs):
        traces = task.outputs.get("model_execution", [])
        prior = next(
            trace for trace in reversed(traces)
            if isinstance(trace, dict)
            and trace.get("role") == "validator"
            and trace.get("result") == "success"
        )
        # Reuse the exact first response and its trace digest, while emulating a
        # successful cached result (no provider/model invocation in this test).
        content = router.response["content"]
        prior = dict(prior)
        prior["api_result"] = "success"
        prior["result"] = "success"
        prior["response_sha256"] = task_roles.hashlib.sha256(content.encode("utf-8")).hexdigest()
        prior["output_contract_gate"] = {"status": "pass", "reason": "cached fixture"}
        traces.append(prior)
        task.outputs["model_execution"] = traces
        return {"success": True, "content": content, "provider": "fixture", "model": "cached", "tried_models": []}

    monkeypatch.setattr(task_roles, "_record_model_execution", accepted_cached_validator_response)
    # Re-audit the exact same valid Validator response without consuming a
    # second provider call; this checks rebinding against the persisted shadow.
    second = Validator(pool, llm_router=router).validate_task(after_first)
    after_second = pool.load_task(task_id)

    assert after_second is not None
    audit = after_second.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert audit["role_audits"]["researcher"]["binding_valid"] is True
    assert audit["role_audits"]["validator"]["binding_valid"] is True
    assert after_second.outputs["validator_neuro_symbolic_audit_task_id"] == task_id
    assert after_second.outputs["neuro_symbolic_audit_task_id"] == task_id
    assert second["passed"] is True


def test_same_subject_claim_conflict_is_reported_without_choosing_winner(tmp_path):
    pool, task_id, router = _task_with_research(
        tmp_path,
        {"symbolic_claims": [{
            "claim_id": "shared",
            "subject": "source record",
            "predicate": "has label",
            "object": "alpha",
            "polarity": "REFUTES",
            "epistemic_status": "FACT",
            "evidence_refs": ["test:lifecycle-evidence"],
            "premise_ids": [],
            "falsifiable_if": "the source cannot be located",
        }]},
    )

    Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    stored = pool.load_task(task_id)
    assert router.calls == 1
    assert stored is not None
    combined = stored.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert combined["status"] == "NEEDS_REVIEW"
    assert combined["conflicts"][0]["claim_ids"] == [
        "researcher:source_fact", "validator:shared"
    ]
    assert {claim["validation_status"] for claim in combined["claims"]} == {"NEEDS_REVIEW"}
    assert stored.outputs["last_validator_result"]["outcome"] == "approved"
    assert combined["execution_authorized"] is False
    assert combined["promotion_authorized"] is False


def test_validator_cannot_reference_missing_bound_researcher_claim(tmp_path):
    pool, task_id, router = _task_with_research(
        tmp_path,
        {"symbolic_claims": [{
            "claim_id": "derived",
            "subject": "source record",
            "predicate": "has unresolved extension",
            "object": "beta",
            "polarity": "SUPPORTS",
            "epistemic_status": "INFERENCE",
            "evidence_refs": [],
            "premise_ids": ["researcher:ghost"],
            "falsifiable_if": "the referenced researcher claim is absent",
        }]},
    )

    result = Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    stored = pool.load_task(task_id)

    assert stored is not None
    validator_audit = stored.outputs["validator_neuro_symbolic_audit"]
    combined = stored.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert validator_audit["status"] == "INVALID"
    assert any(
        issue["code"] == "UNRESOLVED_PREMISE_REF"
        for issue in validator_audit["issues"]
    )
    assert combined["status"] == "INVALID"
    assert any(
        issue["code"] == "UNRESOLVED_PREMISE_REF"
        and issue["field"] == "researcher:ghost"
        for issue in combined["issues"]
    )
    assert any(
        issue["code"] == "ROLE_AUDIT_INVALID" and issue["field"] == "validator"
        for issue in combined["issues"]
    )
    assert combined["promotion_authorized"] is False
    # Typed symbolic claims are an advisory shadow; ordinary Validator approval
    # still follows its hard-objection/evidence gate, not this metadata audit.
    assert result["passed"] is True
    assert stored.outputs["last_validator_result"]["outcome"] == "approved"


def test_tampered_validator_shadow_cannot_bind_to_replayed_response(tmp_path, monkeypatch):
    pool, task_id, router = _task_with_research(tmp_path, None)
    first = Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    stored = pool.load_task(task_id)
    assert stored is not None
    assert first["passed"] is True

    forged_shadow = dict(stored.outputs["validator_neuro_symbolic_audit"])
    forged_shadow["claims"] = []
    stored.outputs["validator_neuro_symbolic_audit"] = forged_shadow
    assert pool.update_task(stored)

    import core.task_roles as task_roles

    def replay_validator_response(task, _role, _router, _prompt, **_kwargs):
        prior = next(
            trace for trace in reversed(task.outputs.get("model_execution", []))
            if isinstance(trace, dict)
            and trace.get("role") == "validator"
            and trace.get("result") == "success"
        )
        content = router.response["content"]
        replayed = dict(prior)
        replayed["api_result"] = "success"
        replayed["result"] = "success"
        replayed["response_sha256"] = task_roles.hashlib.sha256(content.encode("utf-8")).hexdigest()
        replayed["output_contract_gate"] = {"status": "pass", "reason": "cached fixture"}
        task.outputs.setdefault("model_execution", []).append(replayed)
        return {"success": True, "content": content, "provider": "fixture", "model": "cached"}

    monkeypatch.setattr(task_roles, "_record_model_execution", replay_validator_response)
    Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    after_replay = pool.load_task(task_id)

    assert after_replay is not None
    joint = after_replay.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert joint["role_audits"]["researcher"]["binding_valid"] is True
    assert joint["role_audits"]["validator"]["binding_valid"] is False
    assert joint["status"] == "INVALID"
    assert any(
        issue["code"] == "ROLE_AUDIT_INVALID" and issue["field"] == "validator"
        for issue in joint["issues"]
    )
    assert joint["promotion_authorized"] is False


def test_invalid_validator_claim_does_not_contaminate_current_research_claim(tmp_path):
    pool, task_id, router = _task_with_research(
        tmp_path,
        {"symbolic_claims": [{
            "claim_id": "bad",
            "subject": "unresolved proposition",
            "predicate": "is",
            "object": "unverified",
            "polarity": "SUPPORTS",
            "epistemic_status": "FACT",
            "evidence_refs": ["invented:source"],
            "premise_ids": [],
            "falsifiable_if": "source cannot be located",
        }]},
    )

    Validator(pool, llm_router=router).validate_task(pool.load_task(task_id))
    stored = pool.load_task(task_id)
    assert stored is not None
    combined = stored.outputs["last_validator_result"]["neuro_symbolic_audit"]
    assert combined["status"] == "INVALID"
    assert any(
        issue["code"] == "ROLE_AUDIT_INVALID" and issue["field"] == "validator"
        for issue in combined["issues"]
    )
    assert combined["role_audits"]["researcher"]["binding_valid"] is True
    assert combined["role_audits"]["validator"]["binding_valid"] is True
    assert combined["promotion_authorized"] is False
    # The optional symbolic trace cannot bypass or rewrite the extant Validator
    # outcome; the genuine independently sourced evidence still controls review.
    assert stored.outputs["last_validator_result"]["outcome"] == "approved"
