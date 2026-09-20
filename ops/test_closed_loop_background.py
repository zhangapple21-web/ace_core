import json

from core.closed_loop_background import ClosedLoopBackgroundRunner
from core.closed_loop_engine import ClosedLoopEngine


class FakePool:
    available_providers = ["oneapi", "shenwen", "glm"]

    def multi_chat(self, **kwargs):
        return [
            {"provider": "oneapi", "model": "gpt-5.6-terra", "content": json.dumps({
                "work_items": [
                    {"objective": "复现问题", "acceptance": "有可重跑基线", "risk": "low"},
                    {"objective": "做一个最小改动", "acceptance": "有回滚点", "risk": "medium"},
                ],
                "baseline_metrics": [{"name": "success_rate", "direction": "higher", "measurement": "同一固定样本"}],
                "change_boundary": "只改一处",
                "unknowns": [],
            })}
        ]


class FakeTask:
    task_id = "TASK-CLOSED-1"


class FakeTaskPool:
    def __init__(self):
        self.created = []

    def create_task(self, **kwargs):
        self.created.append(kwargs)
        return FakeTask()


def test_background_runner_uses_pool_and_creates_governed_plan(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    tasks = FakeTaskPool()
    runner = ClosedLoopBackgroundRunner(engine, FakePool(), tasks)
    proposal = {"status": "OBSERVED", "proposal": {
        "fingerprint": "abc123",
        "proposal_id": "SEP-1",
        "title": "验证路由",
        "objective": "降低失败率",
        "reason": "出现重复失败",
        "priority": "high",
        "evidence": [],
    }}
    result = runner.run_once(proposal)
    assert result["status"] == "PLANS_READY_FOR_TASK_POOL_REVIEW"
    assert result["provider_calls"] == 1
    assert tasks.created[0]["creator"] == "closed_loop_background"
    assert runner.run_once(proposal)["status"] == "ALREADY_PLANNED"


def test_invalid_model_plan_is_blocked(tmp_path):
    class InvalidPool(FakePool):
        def multi_chat(self, **kwargs):
            return [{"provider": "oneapi", "model": "x", "content": "not json"}]

    runner = ClosedLoopBackgroundRunner(ClosedLoopEngine(tmp_path / "ace"), InvalidPool(), FakeTaskPool())
    result = runner.run_once({"status": "OBSERVED", "proposal": {"fingerprint": "bad", "objective": "x"}})
    assert result["status"] == "BLOCKED_NO_VALID_PLAN"
    assert result["invalid_candidates"] == 1
