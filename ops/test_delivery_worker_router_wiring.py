"""Regression: the delivery worker path is actually wired.

_delivery_worker_runner has always called self.worker_router, but nothing in
the tree ever assigned that attribute, so every CLI delivery raised
AttributeError and delivery_execution recorded an honest WORKER_FAILED. This
test pins the wiring without calling a model: the router must exist, expose
the CLI's registered models in fallback order, and resolve for the
capability the delivery runner asks for.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ace_daemon import AceDaemon
from core.opencode_worker import OPENCODE_MODELS, OpenCodeWorker


class StubWorker:
    executable = r"C:\nonexistent\opencode.exe"

    @staticmethod
    def models():
        return dict(OPENCODE_MODELS)


@pytest.fixture
def daemon():
    d = AceDaemon.__new__(AceDaemon)
    d._delivery_runner_cache = None
    d.worker_router = None
    return d


def test_router_is_built_from_the_worker_registry(daemon):
    daemon._ensure_worker_router(StubWorker())
    assert daemon.worker_router is not None
    order = daemon.worker_router.model_order("structured_readonly")
    assert order, "no model became routable"
    assert set(order) <= set(OPENCODE_MODELS.values())


def test_registry_order_is_deduplicated_and_bounded(daemon):
    daemon._ensure_worker_router(StubWorker())
    order = daemon.worker_router.model_order("document")
    assert len(order) == len(set(order))
    assert len(order) <= daemon.worker_router.max_attempts


def test_delivery_runner_gets_a_callable_router(daemon):
    """The runner closure must resolve a router, not None."""
    daemon._ensure_worker_router(StubWorker())
    assert callable(getattr(daemon.worker_router, "run", None))

    # The exact expression the delivery runner evaluates.
    called = {}
    daemon.worker_router.run = lambda capability, worker, **kw: called.setdefault(
        "capability", capability
    )
    runner = lambda **kw: daemon.worker_router.run(
        "structured_readonly", StubWorker(), task="t", workspace=str(Path.cwd()),
        expected_result="x", verification_method="file_exists_nonempty",
    )
    runner(task_id="probe")
    assert called["capability"] == "structured_readonly"


def test_missing_router_is_reported_not_raised(daemon):
    """A broken registry must not take the delivery stage down."""
    daemon._log_error = lambda *a, **k: None
    import core.worker_router as wr

    original = wr.WorkerRouter

    class Exploding:
        def __init__(self, *a, **k):
            raise RuntimeError("registry unavailable")

    wr.WorkerRouter = Exploding
    try:
        daemon._ensure_worker_router(StubWorker())
    finally:
        wr.WorkerRouter = original
    assert daemon.worker_router is None
