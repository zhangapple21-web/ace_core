import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.task import Task
from ops.test_support import FixtureTaskPool
from core.task_roles import _record_model_execution


class _FakeRouter:
    def chat(self, **_kwargs):
        return {
            "success": True,
            "content": "bounded result",
            "provider": "test-provider",
            "model": "test-model",
            "usage": {},
            "cost": {},
            "latency_ms": 1,
            "attempts": [{"number": 1, "success": True}],
            "tried_models": ["test-provider:test-model"],
        }


def _wire_fake_miner_pool(daemon, miner_pool):
    daemon.miner_pool = miner_pool
    daemon.researcher.llm_router = miner_pool
    daemon.validator.llm_router = miner_pool


def test_trace_writer_records_only_explicit_ace_local_run_identity():
    task = Task(
        task_id="RQ-run-attribution",
        title="trace attribution fixture",
        hypothesis="local run identity is explicit",
        tags=["task_type:strategic"],
    )

    _record_model_execution(
        task,
        "researcher",
        _FakeRouter(),
        "fixture prompt",
        ace_local_run_id="run-A",
    )

    trace = task.outputs["model_execution"][0]
    assert trace["ace_local_run_id"] == "run-A"
    assert "request_id" not in trace
    assert "prompt" not in trace


def test_existing_daemon_identity_is_injected_into_future_admitted_traces():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.task_pool = FixtureTaskPool(Path(temp_dir) / "task_pool")
        daemon.run_id = "run-A"
        _wire_fake_miner_pool(daemon, _FakeRouter())
        task = daemon.task_pool.create_task(
            "run attribution fixture",
            hypothesis="future admitted traces use the existing daemon identity",
            priority="high",
            creator="test",
            tags=["task_type:strategic"],
        )

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        assert stored.outputs["model_execution"]
        assert all(trace["ace_local_run_id"] == "run-A" for trace in stored.outputs["model_execution"])



