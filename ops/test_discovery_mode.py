#!/usr/bin/env python3
import ast
import json
import sys
import textwrap
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.discovery import DiscoveryCandidate, DiscoveryMode
from core.miner_pool.model_router import ModelRouter
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.task import TaskPool
from core.task_roles import Archivist, Guardian, Researcher, Validator


def load_daemon_class():
    source_path = Path(__file__).resolve().parent.parent / "ace_daemon.py"
    source = source_path.read_text(encoding="utf-8")
    module = ast.parse(source)
    class_node = next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "AceDaemon"
    )
    methods = {
        node.name: ast.get_source_segment(source, node)
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_lifecycle_lock_owner_alive",
            "_acquire_lifecycle_lock",
            "_release_lifecycle_lock",
            "_run_task_lifecycle",
            "_run_autonomous_loop",
            "_execute_task_with_worker",
        }
    }
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "json": json,
        "os": __import__("os"),
        "time": __import__("time"),
    }
    daemon_class = type("AceDaemon", (), {})
    for name in (
        "_lifecycle_lock_owner_alive",
        "_acquire_lifecycle_lock",
        "_release_lifecycle_lock",
        "_run_task_lifecycle",
        "_run_autonomous_loop",
        "_execute_task_with_worker",
    ):
        method_namespace = dict(namespace)
        exec(textwrap.dedent(methods[name]), method_namespace)
        setattr(daemon_class, name, method_namespace[name])
    return daemon_class


AceDaemon = load_daemon_class()


class MemoryIndex:
    def __init__(self):
        self.archives = []

    def search(self, keyword="", limit=10, **kwargs):
        return [
            {
                "content": f"Evidence for {keyword} confirms the repository path.",
                "source": "isolated_memory",
                "title": "isolated evidence",
            },
            {
                "content": f"Independent evidence for {keyword} confirms the boundary.",
                "source": "isolated_memory",
                "title": "isolated countercheck",
            },
        ]

    def add(self, **kwargs):
        self.archives.append(kwargs)


def candidate(fingerprint, title):
    return DiscoveryCandidate(
        fingerprint=fingerprint,
        title=title,
        description=f"Static repository evidence found for {title}.",
        reason="The isolated audit found an execution boundary that needs review.",
        objective="Record the evidence and validate the existing lifecycle path.",
        completion_criteria="The task reaches the existing archive stage with its discovery metadata intact.",
        verification_method="Inspect task status, archive record, and stored router decision.",
    )


def verify_autonomous_maintenance_contract(root):
    task_pool = TaskPool(str(root / "contract_task_pool"))
    observer = RuntimeObserver(str(root / "contract_observations"))
    converter = ObservationToTaskConverter(observer=observer, task_pool=task_pool)
    complete_candidate = DiscoveryCandidate(
        fingerprint="autonomous-maintenance-contract",
        title="Verify autonomous maintenance contract",
        description="Runtime audit found a reproducible maintenance gap.",
        reason="The observation is evidence-backed and the TaskPool is idle.",
        objective="Persist a complete, auditable maintenance task contract.",
        completion_criteria="The task stores all required autonomous maintenance fields.",
        verification_method="Inspect the persisted TaskPool task outputs.",
        metadata={
            "autonomous_maintenance": {
                "why_now": "The runtime audit found an actionable gap while no viable work exists.",
                "evidence": [{"source": "runtime_audit", "detail": "reproducible maintenance gap"}],
                "priority": "high",
                "expected_result": "A fully explained maintenance task is persisted.",
                "verification_method": "Inspect the persisted TaskPool task outputs.",
                "risk": "Low; metadata-only task creation.",
                "source": "runtime_audit",
                "estimated_scope": "focused converter contract",
            }
        },
    )
    invalid_candidate = DiscoveryCandidate(
        fingerprint="autonomous-maintenance-contract-invalid",
        title="Reject unsupported maintenance task",
        description="A maintenance idea without supporting evidence.",
        reason="No verified evidence supports dispatching work now.",
        objective="This candidate must remain an observation.",
        completion_criteria="No TaskPool task is created.",
        verification_method="Inspect the TaskPool.",
        metadata={
            "autonomous_maintenance": {
                "why_now": "An idea was recorded.",
                "evidence": [],
                "priority": "high",
                "expected_result": "No task is created.",
                "verification_method": "Inspect the TaskPool.",
                "risk": "Task churn.",
                "source": "unverified_idea",
                "estimated_scope": "none",
            }
        },
    )
    discovery = DiscoveryMode(
        task_pool=task_pool,
        observer=observer,
        base_dir=str(root),
        candidate_sources=[lambda: [complete_candidate, invalid_candidate]],
    )

    assert discovery.discover()["status"] == "observed"
    assert converter.convert()["tasks_created"] == 1
    task = task_pool.list_tasks(status="pending", limit=1)[0]
    assert task.outputs["autonomous_maintenance"] == complete_candidate.metadata["autonomous_maintenance"]
    task = task_pool.move_task(task.task_id, "active", actor="test")
    task = task_pool.move_task(task.task_id, "review", actor="test", task=task)
    task = task_pool.move_task(task.task_id, "approved", actor="test", task=task)
    task_pool.move_task(task.task_id, "archived", actor="test", task=task)

    assert discovery.discover()["status"] == "observed"
    rejected = converter.convert()
    assert rejected["tasks_created"] == 0
    assert rejected["details"] == [{
        "obs_id": rejected["details"][0]["obs_id"],
        "rule": "discovery_candidate",
        "reason": "invalid_autonomous_maintenance_contract",
    }]
    assert not task_pool.list_tasks(status="pending")


def complete_lifecycle(task_pool, memory_index):
    researcher = Researcher(task_pool=task_pool, memory_index=memory_index)
    validator = Validator(task_pool=task_pool, memory_index=memory_index)
    guardian = Guardian(task_pool=task_pool, memory_index=memory_index)
    archivist = Archivist(task_pool=task_pool, memory_index=memory_index)

    task = researcher.pick_up_task(priority="any")
    assert task is not None
    for _ in range(3):
        researcher.research_task(task)
        task = task_pool.list_tasks(status="review", limit=1)[0]
        validator.validate_task(task)
        approved = task_pool.list_tasks(status="approved", limit=1)
        if approved:
            task = approved[0]
            break
        pending = task_pool.list_tasks(status="pending", limit=1)[0]
        assert pending.retry_after
        pending.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        task_pool.update_task(pending)
        task = researcher.pick_up_task(priority="any")
        assert task is not None
    else:
        raise AssertionError("isolated task did not pass validation")
    guardian.judge(task)
    task = task_pool.list_tasks(status="approved", limit=1)[0]
    assert archivist.archive_task(task)


def make_lock_daemon(lock_file):
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.lifecycle_lock_file = lock_file
    daemon.lifecycle_lock_token = None
    return daemon


def verify_legacy_delegation(root):
    source = (Path(__file__).resolve().parent.parent / "ace_daemon.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    class_node = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "AceDaemon")
    methods = {
        node.name: ast.get_source_segment(source, node)
        for node in class_node.body
        if isinstance(node, ast.FunctionDef)
    }
    loop_source = methods["_run_autonomous_loop"]
    worker_source = methods["_execute_task_with_worker"]
    run_once_source = methods["run_once"]
    assert "_run_task_lifecycle()" in loop_source
    assert "_run_autonomous_loop(" not in run_once_source
    assert "create_worker" not in loop_source
    assert "create_worker" not in worker_source
    assert "superseded_by_task_lifecycle" in worker_source

    daemon = AceDaemon.__new__(AceDaemon)
    daemon._run_task_lifecycle = lambda: {"researched": 1, "archived": 1}
    result = daemon._run_autonomous_loop()
    assert result["delegated_to"] == "task_lifecycle"
    assert result["tasks_executed"] == 1

    task_pool = TaskPool(str(root / "legacy_task_pool"))
    task = task_pool.create_task(title="Legacy worker bypass", creator="test")
    daemon.task_pool = task_pool
    blocked = daemon._execute_task_with_worker(task)
    assert blocked["reason"] == "superseded_by_task_lifecycle"
    assert task_pool.load_task(task.task_id).status == "pending"


def verify_restart_lock(root):
    lock_file = root / "task_pool" / ".lifecycle.lock"
    first = make_lock_daemon(lock_file)
    second = make_lock_daemon(lock_file)
    assert first._acquire_lifecycle_lock()
    assert not second._acquire_lifecycle_lock()
    first._release_lifecycle_lock()
    assert second._acquire_lifecycle_lock()
    second._release_lifecycle_lock()

    lock_file.write_text(json.dumps({"pid": 99999999, "token": "stale"}), encoding="utf-8")
    restarted = make_lock_daemon(lock_file)
    assert restarted._acquire_lifecycle_lock()
    restarted._release_lifecycle_lock()


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        (root / "ace_daemon.py").write_text(
            "def _run_autonomous_loop():\n    create_worker()\n",
            encoding="utf-8",
        )
        task_pool = TaskPool(str(root / "task_pool"))
        observer = RuntimeObserver(str(root / "observations"))
        converter = ObservationToTaskConverter(observer=observer, task_pool=task_pool)
        router = ModelRouter(available_providers=["github_models"])
        candidates = [
            candidate("isolated-router-gap", "Audit router boundary"),
            candidate("isolated-experience-gap", "Audit experience feedback"),
        ]
        discovery = DiscoveryMode(
            task_pool=task_pool,
            observer=observer,
            base_dir=str(root),
            model_router=router,
            candidate_sources=[lambda: candidates],
        )
        memory_index = MemoryIndex()
        verify_legacy_delegation(root)
        verify_restart_lock(root)
        verify_autonomous_maintenance_contract(root)

        pending = task_pool.create_task(title="Existing work", priority="high", creator="test")
        assert discovery.discover()["reason"] == "viable_task_exists"
        task_pool.move_task(pending.task_id, "rejected", actor="test")
        task_pool.move_task(pending.task_id, "graveyard", actor="test")

        blocked = task_pool.create_task(title="Blocked work", priority="high", creator="test")
        task_pool.move_task(blocked.task_id, "blocked", actor="test")
        assert discovery.discover()["reason"] == "viable_task_exists"
        task_pool.move_task(blocked.task_id, "rejected", actor="test")
        task_pool.move_task(blocked.task_id, "graveyard", actor="test")

        first = discovery.discover()
        assert first["status"] == "observed"
        assert converter.convert()["tasks_created"] == 1
        first_task = task_pool.list_tasks(status="pending", limit=1)[0]
        first_metadata = first_task.outputs["discovery"]
        assert first_metadata["fingerprint"] == "isolated-router-gap"
        assert first_metadata["reason"]
        assert first_metadata["objective"]
        assert first_metadata["completion_criteria"]
        assert first_metadata["verification_method"]
        assert first_metadata["priority"] == "high"
        assert first_metadata["route"]["boundary"] == "ModelRouter"
        assert first_metadata["route"]["selected_model"] == "github_models:gpt-4o"
        complete_lifecycle(task_pool, memory_index)
        assert len(task_pool.list_tasks(status="archived")) == 1

        second = discovery.discover()
        assert second["status"] == "observed"
        assert converter.convert()["tasks_created"] == 1
        second_task = task_pool.list_tasks(status="pending", limit=1)[0]
        assert second_task.outputs["discovery"]["fingerprint"] == "isolated-experience-gap"
        complete_lifecycle(task_pool, memory_index)

        final = discovery.discover()
        assert final == {
            "status": "no_action",
            "reason": "no_evidence_backed_candidate",
            "candidate": None,
            "observation_id": None,
        }
        assert len(task_pool.list_tasks(status="archived")) == 2
        assert len(memory_index.archives) == 2

    print("isolated discovery and legacy delegation lifecycle passed")


if __name__ == "__main__":
    main()
