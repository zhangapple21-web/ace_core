import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_task_admission import ModelTaskAdmission
from core.task import TaskPool


def valid_candidate():
    return {
        "source_type": "external_research",
        "source_ref": "obs-model-worthy-1",
        "evidence": [
            {
                "source_ref": "runtime:health-1",
                "detail": "Observed repeated divergence.",
            },
            {
                "source_ref": "archive:incident-9",
                "detail": "Prior incident leaves an unresolved cause.",
            },
        ],
        "research_question": "What explains the repeated divergence?",
        "expected_result": "A falsifiable explanation with evidence gaps.",
        "verification_method": "Compare the explanation against both source records.",
    }


def persist_if_eligible(pool, candidate):
    decision = ModelTaskAdmission().evaluate(candidate)
    if not decision["eligible"]:
        return None
    return pool.create_task(
        title="Investigate observed divergence",
        hypothesis=candidate["research_question"],
        creator="test",
        priority="high",
        tags=["task_type:reasoning", f"from_obs:{candidate['source_ref']}"],
        admission={
            "source_type": candidate["source_type"],
            "source_ref": candidate["source_ref"],
            "why_now": candidate["research_question"],
            "evidence": candidate["evidence"],
            "expected_result": candidate["expected_result"],
            "verification_method": candidate["verification_method"],
            "risk": "Isolated test task only.",
            "estimated_scope": "one admission decision",
        },
        outputs={
            "discovery": {"task_type": "reasoning"},
            "model_task_admission": decision,
        },
    )


def test_two_independent_evidence_records_are_reasoning_eligible():
    decision = ModelTaskAdmission().evaluate(valid_candidate())

    assert decision["eligible"] is True
    assert decision["classification"] == "reasoning"
    assert decision["evidence_refs"] == ["runtime:health-1", "archive:incident-9"]


def test_eligible_candidate_persists_a_traceable_reasoning_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        task = persist_if_eligible(TaskPool(temp_dir), valid_candidate())

        assert task is not None
        assert "task_type:reasoning" in task.tags
        assert task.outputs["discovery"]["task_type"] == "reasoning"
        assert task.outputs["model_task_admission"]["eligible"] is True
        assert task.outputs["admission"]["source_ref"] == "obs-model-worthy-1"
        assert task.outputs["admission"]["evidence"] == valid_candidate()["evidence"]


def test_discovery_route_mode_does_not_make_candidate_local_only():
    candidate = valid_candidate()
    candidate["route_mode"] = "local_evidence_only"

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is True
    assert decision["classification"] == "reasoning"


def test_explicit_local_only_candidate_is_not_model_eligible():
    candidate = valid_candidate()
    candidate["local_evidence_only"] = True

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is False
    assert decision["reasons"] == ["local_evidence_only"]


def test_single_evidence_record_is_not_model_eligible():
    candidate = valid_candidate()
    candidate["evidence"] = candidate["evidence"][:1]

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is False
    assert decision["classification"] == "local_evidence_only"
    assert "independent_evidence_required" in decision["reasons"]


def test_missing_verification_method_is_not_model_eligible():
    candidate = valid_candidate()
    candidate["verification_method"] = ""

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is False
    assert "verification_method_required" in decision["reasons"]


def test_archaeology_cannot_be_promoted_to_reasoning():
    candidate = valid_candidate()
    candidate["source_type"] = "archaeology"
    candidate["task_type"] = "reasoning"

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision == {
        "eligible": False,
        "classification": "local_evidence_only",
        "reasons": ["local_evidence_only"],
        "evidence_refs": ["runtime:health-1", "archive:incident-9"],
        "admission_basis": {
            "source_ref": "obs-model-worthy-1",
            "source_type": "archaeology",
        },
    }


def test_strategic_and_execution_claims_do_not_upgrade_isolated_tasks():
    for requested_type in ("strategic", "execution"):
        candidate = valid_candidate()
        candidate["task_type"] = requested_type

        decision = ModelTaskAdmission().evaluate(candidate)

        assert decision["eligible"] is False
        assert decision["classification"] == "local_evidence_only"
        assert "model_role_contract_required" in decision["reasons"]
        assert decision["classification"] not in {"strategic", "execution"}


def test_strategic_requires_explicit_l2_value_contract():
    candidate = valid_candidate()
    candidate["task_type"] = "strategic"
    candidate["evidence"].append({"source_ref": "review:third", "detail": "third independent review"})
    candidate["model_work_contract"] = {
        "value_level": "L2_STRATEGIC",
        "impact_scope": "runtime and data production boundaries",
        "alternatives": ["retain current role", "adopt bounded failover"],
        "counter_evidence": "The latest successful run may invalidate the incident.",
        "decision_verification": "Compare both alternatives against three artifacts.",
    }

    decision = ModelTaskAdmission().evaluate(candidate)
    assert decision["eligible"] is True
    assert decision["classification"] == "strategic"


def test_execution_requires_authorized_reversible_l3_contract():
    candidate = valid_candidate()
    candidate["task_type"] = "execution"
    candidate["evidence"].append({"source_ref": "approval:third", "detail": "approved evidence"})
    candidate["model_work_contract"] = {
        "value_level": "L3_EXECUTION",
        "approved_parent_task_id": "RQ-20260825-021",
        "authorization_scope": "local reversible configuration only",
        "rollback_plan": "Restore the exact prior configuration artifact.",
        "execution_verification": "Run bounded regressions and compare hashes.",
    }

    decision = ModelTaskAdmission().evaluate(candidate)
    assert decision["eligible"] is True
    assert decision["classification"] == "execution"


def test_rejected_inputs_never_create_isolated_tasks():
    single_evidence = valid_candidate()
    single_evidence["evidence"] = single_evidence["evidence"][:1]
    archaeology = valid_candidate()
    archaeology["source_type"] = "archaeology"

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        assert persist_if_eligible(pool, single_evidence) is None
        assert persist_if_eligible(pool, archaeology) is None

        assert pool.list_tasks(status="pending", limit=10) == []
