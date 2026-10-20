"""Regression contracts for model-result gating and rework scheduling."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task import Task
from core.task_roles import Researcher, Validator, _record_model_execution
from ops.test_support import FixtureTaskPool


class _Router:
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def chat(self, **_kwargs):
        self.calls += 1
        return dict(self.response)


def _admission(source_ref: str) -> dict:
    return {
        "source_type": "system_observation",
        "source_ref": source_ref,
        "why_now": "A focused regression must verify this path.",
        "evidence": [{"source_ref": source_ref, "description": "Test fixture only."}],
        "expected_result": "The task follows the model-result contract.",
        "verification_method": "Run the focused pytest case.",
        "risk": "Test-only data.",
        "estimated_scope": "one task",
    }


def _response(*, content: str, provider: str = "shenwen", model: str = "gpt-6.1-sol") -> dict:
    return {
        "success": True,
        "content": content,
        "provider": provider,
        "model": model,
        "latency_ms": 1,
        "tried_models": [f"{provider}:{model}"],
        "attempts": [],
        "usage": {},
        "cost": {},
    }


def test_profile_disallowed_response_is_not_returned_as_a_model_result():
    task = Task(
        "RQ-model-gate-unit",
        "execution-profile response gate",
        hypothesis="Only an allowed execution profile result may be consumed.",
        tags=["task_type:execution"],
        outputs={"discovery": {"task_type": "execution"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content='{"facts":["untrusted route"]}'))

    result = _record_model_execution(task, "researcher", router, "fixture")

    assert router.calls == 1
    assert result is None
    trace = task.outputs["model_execution"][-1]
    assert trace["api_result"] == "success"
    assert trace["result"] == "failed"
    assert trace["quality_gate"]["executed"] is False
    assert trace["error"] == "selected provider/model violates task profile"


def test_successful_but_empty_model_content_is_not_a_model_result():
    task = Task(
        "RQ-model-gate-empty",
        "execution-profile empty result gate",
        hypothesis="An empty completion is not usable output.",
        tags=["task_type:execution"],
        outputs={"discovery": {"task_type": "execution"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content="", provider="glm", model="glm-4-flash"))

    result = _record_model_execution(task, "researcher", router, "fixture")

    assert result is None
    trace = task.outputs["model_execution"][-1]
    assert trace["api_result"] == "success"
    assert trace["result"] == "failed"
    assert trace["quality_gate"]["executed"] is False


def test_validator_response_missing_fields_are_reported_in_output_gate():
    task = Task(
        "RQ-validator-missing-fields",
        "validator missing fields",
        hypothesis="Missing validator material must remain visible on the trace.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content="{malformed-json"))

    response = _record_model_execution(task, "validator", router, "fixture")
    gate = task.outputs["model_execution"][-1]["output_contract_gate"]

    assert response is None
    assert gate["status"] == "fail"
    assert gate["reason"] == "response_not_json"
    assert set(gate["missing_fields"]) == {
        "facts", "evidence", "inference", "unknowns", "objections",
        "next_verification", "stop_condition", "hard_objections",
        "advisory_objections", "counter_examples",
    }


def test_nonempty_but_unstructured_response_fails_output_contract_gate():
    task = Task(
        "RQ-model-gate-structure",
        "execution-profile output contract gate",
        hypothesis="A useful model answer must meet the structured contract.",
        tags=["task_type:execution"],
        outputs={"discovery": {"task_type": "execution"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content="A plain text conclusion." , provider="glm", model="glm-4-flash"))

    result = _record_model_execution(task, "researcher", router, "fixture")
    trace = task.outputs["model_execution"][-1]

    assert result is None
    assert trace["api_result"] == "success"
    assert trace["quality_gate"]["executed"] is True
    assert trace["result"] == "failed"
    assert trace["execution_feedback"]["status"] == "TEXT_UNSTRUCTURED"
    assert trace["output_contract_gate"]["status"] == "fail"


def test_researcher_does_not_persist_unstructured_model_conclusion(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    router = _Router(_response(content="{malformed-json" , provider="glm", model="glm-4-flash"))
    task = pool.create_task(
        "unstructured research",
        hypothesis="An unstructured answer must not become a research result.",
        creator="test",
        priority="high",
        tags=["task_type:reasoning"],
        admission=_admission("test:unstructured-research"),
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None

    result = Researcher(pool, llm_router=router).research_task(claimed)
    stored = pool.load_task(task.task_id)

    assert stored is not None
    assert "model_research_result" not in stored.outputs
    assert stored.result["model_attempted"] is True
    assert stored.result["model_engaged"] is False
    assert stored.result["model_block_reason"] == "model output contract failed: response_not_json"
    assert "Free-form response" not in result["research_summary"]


def test_researcher_rejects_empty_known_contract_fields():
    task = Task(
        "RQ-researcher-empty-contract",
        "empty research fields",
        hypothesis="An empty facts array is not an analysis result.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content='{"facts":[],"unknowns":[]}'))

    response = _record_model_execution(task, "researcher", router, "fixture")

    assert response is None
    trace = task.outputs["model_execution"][-1]
    assert trace["output_contract_gate"]["status"] == "fail"
    assert trace["output_contract_gate"]["reason"] == "empty_research_contract_fields"
    assert trace["output_contract_gate"]["invalid_fields"] == ["facts", "unknowns"]


def test_researcher_stores_symbolic_audit_bound_to_current_model_and_evidence(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    evidence_source = "test:bound-symbolic-evidence"
    claim = {
        "claim_id": "c1",
        "subject": "the admitted record",
        "predicate": "is labeled",
        "object": "fixture",
        "polarity": "SUPPORTS",
        "epistemic_status": "FACT",
        "evidence_refs": [evidence_source],
        "premise_ids": [],
        "falsifiable_if": "the admitted record uses a different label",
    }
    payload = {
        "facts": ["The task carries the declared fixture record."],
        "evidence": ["The source id is available in admission."],
        "inference": ["Only traceability is asserted by this contract."],
        "unknowns": ["Whether the source entails the claim."],
        "objections": ["The test source is only a fixture."],
        "next_verification": "Review the source content.",
        "stop_condition": "Keep semantic support unverified.",
        "symbolic_claims": [claim],
    }
    router = _Router(_response(content=json.dumps(payload)))
    task = pool.create_task(
        "symbolic traceability research",
        hypothesis="A typed claim must point to current admitted evidence.",
        creator="test",
        priority="high",
        tags=["task_type:reasoning"],
        admission={
            **_admission(evidence_source),
            "evidence": [{"source_ref": evidence_source, "content": "Fixture evidence only."}],
        },
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None

    result = Researcher(pool, llm_router=router).research_task(claimed)
    stored = pool.load_task(task.task_id)

    assert stored is not None
    audit = stored.outputs["neuro_symbolic_audit"]
    assert audit["status"] == "TRACEABLE_UNVERIFIED"
    assert audit["claims"][0]["truth_status"] == "UNVERIFIED"
    assert stored.outputs["neuro_symbolic_audit_task_id"] == task.task_id
    assert stored.outputs["neuro_symbolic_audit_model_sha256"] == stored.outputs[
        "model_research_result"
    ]["response_sha256"]
    assert result["neuro_symbolic_audit"] == audit
    assert audit["execution_authorized"] is False
    assert audit["promotion_authorized"] is False


def test_researcher_marks_unknown_symbolic_evidence_refs_invalid(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    payload = {
        "facts": ["The task carries the declared fixture record."],
        "evidence": ["No source exists for this claim."],
        "inference": ["A citation id is unchecked."],
        "unknowns": ["Whether a real source exists."],
        "objections": ["This fixture does not make semantic truth claims."],
        "next_verification": "Resolve provenance.",
        "stop_condition": "Do not call this a fact.",
        "symbolic_claims": [{
            "claim_id": "c1", "subject": "x", "predicate": "is", "object": "y",
            "polarity": "SUPPORTS", "epistemic_status": "FACT",
            "evidence_refs": ["invented:source"], "premise_ids": [],
            "falsifiable_if": "the source cannot be found",
        }],
    }
    router = _Router(_response(content=json.dumps(payload)))
    task = pool.create_task(
        "symbolic unresolved source",
        hypothesis="A model must not invent a resolvable citation.",
        creator="test",
        priority="high",
        tags=["task_type:reasoning"],
        admission=_admission("test:no-symbolic-source"),
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None

    Researcher(pool, llm_router=router).research_task(claimed)
    stored = pool.load_task(task.task_id)

    assert stored is not None
    audit = stored.outputs["neuro_symbolic_audit"]
    assert audit["status"] == "INVALID"
    assert any(issue["code"] == "UNRESOLVED_EVIDENCE_REF" for issue in audit["issues"])
    # The shadow flags provenance shape only; it does not block or override ACE's
    # existing Validator and Guardian acceptance gates.
    assert audit["promotion_authorized"] is False


def test_researcher_allows_partial_nonempty_contract_fields():
    task = Task(
        "RQ-researcher-partial-contract",
        "partial research fields",
        hypothesis="A partial but nonempty research result is allowed.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content='{"facts":["observed fixture"]}'))

    response = _record_model_execution(task, "researcher", router, "fixture")

    assert response is not None
    gate = task.outputs["model_execution"][-1]["output_contract_gate"]
    assert gate["status"] == "pass"
    assert "unknowns" in gate["missing_fields"]


def test_validator_accepts_empty_finding_arrays_with_valid_context():
    task = Task(
        "RQ-validator-empty-findings",
        "empty validator findings",
        hypothesis="Explicit empty arrays mean no model objection was identified.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content=json.dumps({
        "facts": ["Local fixture was inspected."],
        "unknowns": ["No new uncertainty observed."],
        "hard_objections": [],
        "advisory_objections": [],
        "counter_examples": [],
    })))

    response = _record_model_execution(task, "validator", router, "fixture")

    assert response is not None
    gate = task.outputs["model_execution"][-1]["output_contract_gate"]
    assert gate["status"] == "pass"
    assert gate["invalid_fields"] == []


def test_researcher_does_not_consume_experience_only_as_reasoning_contract():
    task = Task(
        "RQ-researcher-role-contract",
        "researcher role contract",
        hypothesis="Researcher must produce at least one research-domain field.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content='{"experience":"A general sentiment, not task analysis."}'))

    response = _record_model_execution(task, "researcher", router, "fixture")

    assert response is None
    trace = task.outputs["model_execution"][-1]
    assert trace["output_contract_gate"]["status"] == "fail"
    assert trace["output_contract_gate"]["reason"] == "no_known_role_contract_fields"


def test_validator_rejects_invalid_objection_array_types():
    task = Task(
        "RQ-validator-invalid-findings",
        "validator finding schema",
        hypothesis="Validator findings must be explicit arrays of strings.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content=json.dumps({
        "facts": ["A relevant validation context exists."],
        "unknowns": ["Fixture only."],
        "hard_objections": [],
        "advisory_objections": "looks fine",
        "counter_examples": [],
    })))

    response = _record_model_execution(task, "validator", router, "fixture")

    assert response is None
    gate = task.outputs["model_execution"][-1]["output_contract_gate"]
    assert gate["status"] == "fail"
    assert gate["reason"] == "invalid_validator_finding_types"
    assert gate["invalid_fields"] == ["advisory_objections"]


def test_validator_requires_explicit_objection_and_counterexample_arrays():
    task = Task(
        "RQ-validator-role-contract",
        "validator role contract",
        hypothesis="Validator model output must expose review-specific findings.",
        tags=["task_type:reasoning"],
        outputs={"discovery": {"task_type": "reasoning"}},
        data_class="PUBLIC",
    )
    router = _Router(_response(content=json.dumps({
        "facts": ["Facts alone do not report review findings."],
        "evidence": ["fixture evidence"],
        "unknowns": [],
        "next_verification": "none",
        "stop_condition": "done",
    })))

    response = _record_model_execution(task, "validator", router, "fixture")

    assert response is None
    trace = task.outputs["model_execution"][-1]
    assert trace["output_contract_gate"]["status"] == "fail"
    assert "hard_objections" in trace["output_contract_gate"]["missing_fields"]
    assert "advisory_objections" in trace["output_contract_gate"]["missing_fields"]
    assert "counter_examples" in trace["output_contract_gate"]["missing_fields"]


def test_researcher_does_not_persist_profile_disallowed_model_conclusion(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    router = _Router(_response(content='{"facts":["untrusted route conclusion"]}'))
    task = pool.create_task(
        "profile-gated research",
        hypothesis="An off-profile conclusion must not enter research output.",
        creator="test",
        priority="high",
        tags=["task_type:execution"],
        admission=_admission("test:profile-gated-research"),
        outputs={"discovery": {"task_type": "execution"}},
        data_class="PUBLIC",
    )
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None

    result = Researcher(pool, llm_router=router).research_task(claimed)
    stored = pool.load_task(task.task_id)

    assert router.calls == 1
    assert stored is not None
    assert "model_research_result" not in stored.outputs
    assert stored.result["model_engaged"] is False
    assert stored.result["model_attempted"] is True
    assert "violates task profile" in stored.result["model_block_reason"]
    assert result["evidence_found"] >= 1


def test_validator_does_not_consume_objections_from_a_disallowed_model(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    response = _response(
        content=json.dumps({
            "facts": ["bounded test observation"],
            "evidence": [],
            "unknowns": ["none supplied"],
            "next_verification": "use local evidence gate",
            "hard_objections": ["off-profile objection must not be consumed"],
        })
    )
    router = _Router(response)
    task = pool.create_task(
        "profile-gated validator",
        hypothesis="Three independent records support this bounded fixture.",
        creator="test",
        priority="high",
        tags=["task_type:execution"],
        admission=_admission("test:profile-gated-validator"),
        outputs={"discovery": {"task_type": "execution"}},
        data_class="PUBLIC",
    )
    task.evidence = [
        {"source": "source-a", "content": "Independent evidence from source A. " * 4},
        {"source": "source-b", "content": "Independent evidence from source B. " * 4},
        {"source": "source-c", "content": "Independent evidence from source C. " * 4},
    ]
    task.counter_examples = ["A prior concrete counterexample was recorded."]
    assert pool.update_task(task)
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None
    reviewed = pool.move_task(task.task_id, "review", actor="researcher", task=claimed)
    assert reviewed is not None

    result = Validator(pool, llm_router=router).validate_task(pool.load_task(task.task_id))
    stored = pool.load_task(task.task_id)

    assert router.calls == 1
    assert stored is not None
    assert result["passed"] is True
    assert "off-profile objection must not be consumed" not in result["objections"]
    assert result["hard_objections"] == []
    assert stored.outputs["last_validator_result"]["outcome"] == "approved"


def test_untouched_pending_work_still_precedes_due_rework(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    untouched = pool.create_task("untouched high", creator="test", priority="high")
    rework = pool.create_task("due rework high", creator="test", priority="high")
    rework.last_claimed_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    rework.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    rework.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
    rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    assert pool.update_task(rework)

    candidate = researcher._untouched_candidate(["high"], "excluded")

    assert candidate is not None
    assert candidate.task_id == untouched.task_id


def test_due_pending_rework_remains_available_to_normal_selection(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    rework = pool.create_task("due claimed rework", creator="test", priority="high")
    rework.last_claimed_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    rework.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    rework.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
    rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    assert pool.update_task(rework)

    candidate = researcher._untouched_candidate(["high"], "excluded")

    assert candidate is not None
    assert candidate.task_id == rework.task_id


def test_due_pending_rework_is_claimable_when_it_is_the_only_work(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    rework = pool.create_task("only due rework", creator="test", priority="high")
    rework.last_claimed_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    rework.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    rework.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
    rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    assert pool.update_task(rework)

    claimed = researcher.pick_up_task(priority="any")

    assert claimed is not None
    assert claimed.task_id == rework.task_id
    assert claimed.status == "active"
    assert claimed.lease_owner == "researcher"


def test_pending_rework_waits_until_its_retry_time(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    rework = pool.create_task("not-yet-due rework", creator="test", priority="high")
    rework.last_claimed_at = (datetime.now() - timedelta(minutes=10)).isoformat()
    rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    rework.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    rework.retry_after = (datetime.now() + timedelta(minutes=5)).isoformat()
    rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    assert pool.update_task(rework)

    candidate = researcher._untouched_candidate(["high"], "excluded")

    assert candidate is None
    assert pool.load_task(rework.task_id).status == "pending"


def test_active_rework_with_live_lease_is_not_taken_by_fairness_yield(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    leased = pool.create_task("leased active rework", creator="test", priority="high")
    active = pool.claim_task(leased.task_id, "other-researcher", lease_seconds=60)
    assert active is not None
    active.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    active.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    active.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    assert pool.update_task(active)
    original_claim = active.claim_id
    original_fence = active.fencing_token
    untouched = pool.create_task("untouched pending work", creator="test", priority="high")

    claimed = researcher.pick_up_task(priority="any")
    stored_lease = pool.load_task(leased.task_id)

    assert claimed is not None
    assert claimed.task_id == untouched.task_id
    assert stored_lease.status == "active"
    assert stored_lease.claim_id == original_claim
    assert stored_lease.fencing_token == original_fence
    assert stored_lease.lease_owner == "other-researcher"


def test_expired_active_rework_lease_can_be_claimed_with_new_fencing_token(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    researcher = Researcher(pool)
    task = pool.create_task("expired active rework", creator="test", priority="high")
    active = pool.claim_task(task.task_id, "previous-researcher", lease_seconds=60)
    assert active is not None
    active.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
    active.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
    active.rework_count = researcher.FAIRNESS_REWORK_LIMIT
    active.outputs["last_validator_result"] = {"outcome": "rework_pending"}
    old_claim_id = active.claim_id
    old_fence = active.fencing_token
    assert pool.update_task(active)

    claimed = researcher.pick_up_task(priority="any")

    assert claimed is not None
    assert claimed.task_id == task.task_id
    assert claimed.claim_id != old_claim_id
    assert claimed.fencing_token > old_fence
    assert claimed.lease_owner == "researcher"
