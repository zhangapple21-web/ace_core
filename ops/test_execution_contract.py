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
