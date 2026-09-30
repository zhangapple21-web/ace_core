from core.cognitive_think_gate import (
    CHARTER,
    CONTRACT_VERSION,
    CONVERGED,
    COGNITIVE_HUB,
    JUDGMENT_READY,
    LOOP_BLOCKED,
    NEEDS_HUMAN_DECISION,
    PRODUCTION_LEAF,
    THINK,
    dynamic_think_budget,
    evaluate_cognitive_think_gate,
    sediment_complete,
)
from core.task import Task
from core.task_roles import _record_model_execution


COMPLETE_SEDIMENT = {
    "facts": ["observed"],
    "evidence": ["trace"],
    "inference": ["likely"],
    "unknowns": ["gap"],
    "experience": ["retry later"],
}


def test_hub_default_may_think_and_never_grants_execution():
    result = evaluate_cognitive_think_gate()
    assert result["contract_version"] == CONTRACT_VERSION
    assert result["actor_role"] == COGNITIVE_HUB
    assert result["status"] == THINK
    assert result["thinking_permitted"] is True
    assert result["thinking_grants_execution"] is False
    assert result["execution_permitted"] is False
    assert result["charter"] == CHARTER
    assert "不自动获得执行权" in CHARTER


def test_execution_denied_without_existing_authorization():
    result = evaluate_cognitive_think_gate(execution_requested=True)
    assert result["thinking_grants_execution"] is False
    assert result["execution_permitted"] is False
    assert "EXECUTION_DENIED_BY_THINK_GATE" in result["reason_codes"]


def test_future_behavior_change_requires_complete_sediment():
    incomplete = evaluate_cognitive_think_gate(
        judgment_formed=True,
        judgment_changes_future_behavior=True,
        execution_requested=True,
        existing_execution_authorized=True,
        sediment={"facts": ["x"]},
    )
    assert incomplete["sediment_required"] is True
    assert incomplete["sediment_complete"] is False
    assert incomplete["execution_permitted"] is False
    assert "SEDIMENT_REQUIRED" in incomplete["reason_codes"]
    assert sediment_complete(COMPLETE_SEDIMENT) is True

    ready = evaluate_cognitive_think_gate(
        judgment_formed=True,
        judgment_changes_future_behavior=True,
        unknown_count=0,
        execution_requested=True,
        existing_execution_authorized=True,
        sediment=COMPLETE_SEDIMENT,
    )
    assert ready["status"] == CONVERGED
    assert ready["execution_permitted"] is True
    assert ready["thinking_grants_execution"] is False


def test_production_leaf_has_no_think_right_but_may_use_existing_auth():
    blocked = evaluate_cognitive_think_gate(actor_role=PRODUCTION_LEAF)
    assert blocked["thinking_permitted"] is False
    assert blocked["thinking_grants_execution"] is False
    assert "PRODUCTION_LEAF_HAS_NO_THINK_RIGHT" in blocked["reason_codes"]

    authorized = evaluate_cognitive_think_gate(
        actor_role=PRODUCTION_LEAF,
        execution_requested=True,
        existing_execution_authorized=True,
    )
    assert authorized["thinking_permitted"] is False
    assert authorized["execution_permitted"] is True


def test_no_new_evidence_over_budget_is_loop_blocked():
    budget = dynamic_think_budget(0, "medium")
    blocked = evaluate_cognitive_think_gate(
        think_rounds=budget,
        new_evidence_since_last_think=False,
    )
    assert blocked["status"] == LOOP_BLOCKED
    assert blocked["thinking_permitted"] is False
    assert "THINK_LOOP_BLOCKED" in blocked["reason_codes"]

    recoverable = evaluate_cognitive_think_gate(
        think_rounds=budget,
        new_evidence_since_last_think=True,
    )
    assert recoverable["status"] == THINK
    assert recoverable["thinking_permitted"] is True


def test_human_decision_escalates_without_execution():
    result = evaluate_cognitive_think_gate(
        human_decision_required=True,
        execution_requested=True,
        existing_execution_authorized=True,
        sediment=COMPLETE_SEDIMENT,
        judgment_changes_future_behavior=True,
    )
    assert result["status"] == NEEDS_HUMAN_DECISION
    assert result["thinking_permitted"] is False
    assert result["execution_permitted"] is False
    assert result["next_step"] == "escalate_human_do_not_execute"


def test_judgment_ready_keeps_unknowns_open():
    result = evaluate_cognitive_think_gate(
        judgment_formed=True,
        unknown_count=2,
    )
    assert result["status"] == JUDGMENT_READY
    assert result["thinking_grants_execution"] is False


def test_model_call_is_think_not_execute_and_loop_skips_model():
    class FakeRouter:
        def __init__(self):
            self.calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            return {
                "success": True,
                "content": "plain text without structure",
                "provider": "test",
                "model": "test-model",
                "latency_ms": 1,
                "tried_models": ["test:test-model"],
            }

    task = Task(
        "RQ-think-001",
        "think gate smoke",
        outputs={
            "discovery": {"task_type": "reasoning"},
            "admission": {"source_type": "research"},
        },
    )
    router = FakeRouter()
    first = _record_model_execution(task, "researcher", router, "first")
    assert first is not None
    assert router.calls == 1
    trace = task.outputs["model_execution"][0]
    assert trace["cognitive_think"]["thinking_permitted"] is True
    assert trace["cognitive_think"]["thinking_grants_execution"] is False
    assert trace["cognitive_think"]["execution_permitted"] is False

    second = _record_model_execution(task, "researcher", router, "repair")
    assert second is not None
    assert router.calls == 2
    assert task.outputs["model_execution"][1]["cognitive_think"]["think_rounds"] == 1

    task.outputs["model_execution"] = [
        {"execution_feedback": {"status": "STRUCTURED"}}
        for _ in range(dynamic_think_budget(0, "medium"))
    ]
    blocked = _record_model_execution(task, "researcher", router, "should-not-call")
    assert blocked is None
    assert router.calls == 2
    last = task.outputs["model_execution"][-1]
    assert last["cognitive_think"]["status"] == LOOP_BLOCKED
    assert last["api_called"] is False
