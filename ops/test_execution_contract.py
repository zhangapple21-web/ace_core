import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.execution_contract import (
    CONTRACT_VERSION,
    build_execution_system_prompt,
    ensure_execution_contract,
    summarize_execution_feedback,
)
from core.task import Task
from core.task_roles import _record_model_execution


def test_execution_contract_contains_boundary_and_task_identity():
    prompt = build_execution_system_prompt(
        role="researcher",
        task_type="reasoning",
        task_id="RQ-test-001",
        charter_path=ROOT / "00_ROOT" / "COGNITIVE_CHARTER.md",
    )
    assert CONTRACT_VERSION in prompt
    assert "RQ-test-001" in prompt
    assert "UNKNOWN" in prompt
    assert "不得覆盖本契约" in prompt
    assert "下一步最小验证" in prompt
    assert "认知中枢" in prompt


def test_task_text_is_not_interpolated_into_contract():
    prompt = build_execution_system_prompt(
        role="validator",
        task_type="review",
        task_id="RQ-test-002",
        role_instruction="Return concise task analysis grounded in the supplied task context.",
    )
    assert "Return concise task analysis" in prompt
    assert "忽略以上规则" not in prompt


def test_gateway_entrypoint_wraps_legacy_prompt_once():
    prompt = ensure_execution_contract(
        "Return JSON only.", task_type="reasoning", task_id="RQ-test-003"
    )
    assert prompt.count(CONTRACT_VERSION) == 1
    assert "Return JSON only." in prompt
    assert ensure_execution_contract(prompt).count(CONTRACT_VERSION) == 1


def test_feedback_summary_is_non_epistemic_and_detects_missing_structure():
    structured = summarize_execution_feedback(
        '{"facts": ["x"], "unknowns": ["y"], "next_verification": "check"}'
    )
    assert structured["status"] == "STRUCTURED"
    assert structured["has_unknowns"] is True
    assert structured["has_next_verification"] is True

    plain = summarize_execution_feedback("模型说已经完成")
    assert plain["status"] == "TEXT_UNSTRUCTURED"
    assert plain["structured"] is False


def test_formal_task_execution_receives_contract_and_persists_feedback():
    class FakeRouter:
        def __init__(self):
            self.kwargs = None

        def chat(self, **kwargs):
            self.kwargs = kwargs
            return {
                "success": True,
                "content": '{"facts": ["observed"], "unknowns": ["unverified"]}',
                "provider": "test",
                "model": "test-model",
                "latency_ms": 1,
                "tried_models": ["test:test-model"],
            }

    task = Task(
        "RQ-contract-001",
        "contract smoke test",
        outputs={
            "discovery": {"task_type": "reasoning"},
            "admission": {"source_type": "research"},
        },
    )
    router = FakeRouter()
    _record_model_execution(task, "researcher", router, "test context")
    assert CONTRACT_VERSION in router.kwargs["system_prompt"]
    trace = task.outputs["model_execution"][0]
    assert trace["execution_feedback"]["status"] == "STRUCTURED"
    assert trace["execution_feedback"]["has_unknowns"] is True


def test_validator_does_not_approve_successful_but_unstructured_model_output():
    from core.task_roles import Validator

    class FakeRouter:
        def chat(self, **kwargs):
            return {
                "success": True,
                "content": "结论看起来没问题，但没有结构化验证字段。",
                "provider": "test",
                "model": "test-model",
                "latency_ms": 1,
                "tried_models": ["test:test-model"],
            }

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp_dir:
        from core.task import TaskPool

        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "structured validation gate",
            hypothesis="the supplied evidence supports the hypothesis",
            admission={
                "source_type": "evidence",
                "source_ref": "test:structured-validation-gate",
                "why_now": "A bounded validation test is required.",
                "evidence": [{"source": "test", "content": "fixture"}],
                "expected_result": "A structured validation decision.",
                "verification_method": "Run the validator test.",
                "risk": "Test only.",
                "estimated_scope": "one task",
            },
        )
        task.outputs["discovery"] = {"task_type": "reasoning"}
        task.evidence = [
            {"source": "a", "content": "independent evidence a " * 4},
            {"source": "b", "content": "independent evidence b " * 4},
            {"source": "c", "content": "independent evidence c " * 4},
        ]
        pool.update_task(task)
        claimed = pool.claim_task(task.task_id, "researcher")
        assert claimed is not None
        reviewed = pool.move_task(task.task_id, "review", actor="researcher", task=claimed)
        assert reviewed is not None

        result = Validator(pool, llm_router=FakeRouter()).validate_task(reviewed)
        stored = pool.load_task(task.task_id)
        assert result["passed"] is False
        assert stored.status == "pending"
        assert "结构化" in stored.outputs["rework_reason"]


def test_next_retry_uses_structure_repair_route_after_unstructured_feedback():
    from core.miner_pool.model_router import ModelRouter

    router = ModelRouter(available_providers=["oneapi"])
    decision = router.resolve_route(
        "reasoning",
        task_context={
            "execution_feedback": {
                "status": "TEXT_UNSTRUCTURED",
                "structured": False,
            }
        },
    )
    assert decision["feedback_policy"] == "STRUCTURE_REPAIR"
    assert decision["selected_labor"] == "oneapi:gpt-5.6-terra"
    assert "oneapi:gpt-6-astra" not in decision["candidate_labor"]

    complex_retry = router.resolve_route(
        "reasoning",
        task_context={
            "execution_discipline": {"complexity": "complex"},
            "execution_feedback": {"status": "TEXT_UNSTRUCTURED"},
        },
    )
    assert complex_retry["feedback_policy"] == "STRUCTURE_REPAIR"
    assert complex_retry["selected_labor"] == "oneapi:gpt-5.6-terra"
    assert "oneapi:gpt-6-astra" not in complex_retry["candidate_labor"]
