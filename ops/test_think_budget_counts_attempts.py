# Regression: router-level failures must not burn think budget.
#
# Field evidence: RQ-20261008-022 collected two "no available models"
# traces (the router never reached any model), and those two traces then
# tripped THINK_LOOP_BLOCKED by themselves: think_rounds counted every prior
# trace, including ones where api_called was False. A task that never got to
# think sealed itself shut. Only genuine attempts may consume budget.
from core.task import TaskPool
from core.task_roles import _record_model_execution


class _FakeRouter:
    def __init__(self, content=""):
        self.calls = 0
        self.content = content

    def chat(self, **kwargs):
        self.calls += 1
        return {
            "success": True,
            "content": self.content,
            "model": "test:test-model",
            "provider": "test",
            "usage": {},
            "cost": {},
            "latency_ms": 1,
        }


ADMISSION = {
    "source_type": "maintenance",
    "source_ref": "ops/test_think_budget_counts_attempts.py",
    "why_now": "regression for budget burned by router failures",
    "evidence": ["RQ-20261008-022 sealed itself with two no-model traces"],
    "expected_result": "blocked traces do not consume budget; real attempts do",
    "verification_method": "pytest",
    "risk": "low: test fixtures in tmp_path",
    "estimated_scope": "single-test",
}


def _task(pool, title):
    task = pool.create_task(
        title=title, hypothesis="h", admission=dict(ADMISSION),
        tags=["task_type:reasoning"], data_class="PUBLIC",
    )
    return task


def _blocked_trace():
    return {
        "task_id": "x", "api_called": False, "api_result": "blocked",
        "result": "blocked", "error": "THINK_LOOP_BLOCKED",
        "execution_feedback": {"status": "NONE"},
    }


def test_router_failures_do_not_consume_think_budget(tmp_path):
    from core.task import TaskPool as Pool

    pool = Pool(str(tmp_path / "pool"))
    task = _task(pool, "never reached a model")
    task.outputs.setdefault("model_execution", []).extend(
        [_blocked_trace(), _blocked_trace(), _blocked_trace(), _blocked_trace()]
    )
    assert pool.update_task(task)

    router = _FakeRouter()
    _record_model_execution(task, "researcher", router, "Is the sky blue?")

    assert router.calls == 1, "four blocked traces must not seal the gate"
    assert task.outputs["model_execution"][-1].get("api_called") is True


def test_real_attempts_still_consume_think_budget(tmp_path):
    from core.task import TaskPool as Pool

    pool = Pool(str(tmp_path / "pool"))
    task = _task(pool, "reached models twice")
    router = _FakeRouter()
    _record_model_execution(task, "researcher", router, "First question?")
    assert router.calls == 1
    # The default task draws a budget of one genuine attempt with no new
    # evidence. The second attempt must block at the gate (proving the first
    # one was counted), and the block itself must not consume further.
    _record_model_execution(task, "researcher", router, "Second question?")
    assert router.calls == 1, "the consumed budget must hold the gate shut"
    assert (
        task.outputs["model_execution"][-1].get("error") == "THINK_LOOP_BLOCKED"
    )
