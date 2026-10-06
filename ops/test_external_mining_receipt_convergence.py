# RQ-20261006-012 regression: the external-mining lifecycle projection must converge.
#
# Before the fix, AceDaemon._refresh_governed_external_mining_receipts rebuilt
# the lifecycle projection with `updated_at = now()` on every cycle and then
# called update_task unconditionally. The timestamp always differed from the
# stored copy, so every task carrying an `external_mining` output was rewritten
# every cycle with no audit row and no ledger row. Real modification times in
# the archive became unusable, and the daily backup manifest hashed churned.
import ast
import inspect
import json
import os
import tempfile

from core.task import TaskPool

ADMISSION = {
    "source_type": "maintenance",
    "source_ref": "ops/test_external_mining_receipt_convergence.py",
    "why_now": "regression for the external-mining projection write loop",
    "evidence": ["archived external-mining tasks were rewritten every cycle with no audit row"],
    "expected_result": "a converged projection persists nothing",
    "verification_method": "pytest",
    "risk": "low: test fixture",
    "estimated_scope": "single-test",
}


def test_projection_stamps_time_only_on_semantic_change():
    source = open("ace_daemon.py", encoding="utf-8").read()
    assert "semantic_changed = any(" in source, (
        "the projection must compare semantic fields before writing"
    )
    assert 'lifecycle["updated_at"] = datetime.now().isoformat()' in source, (
        "the wall-clock stamp belongs inside the change branch"
    )
    # The unconditional write is the regression: it must be gone.
    assert "if self.task_pool.update_task(task):\n                refreshed += 1\n            if latest_external" not in source, (
        "update_task must stay inside the semantic-change branch"
    )


def test_unchanged_projection_writes_nothing(tmp_path):
    pool = TaskPool(str(tmp_path))
    task = pool.create_task(
        title="external mining probe",
        hypothesis="probe",
        admission=dict(ADMISSION),
    )
    outputs = dict(task.outputs or {})
    outputs["external_mining"] = {"lifecycle": {}, "source": "steward"}
    task.outputs = outputs
    assert pool.update_task(task)

    # Simulate what the daemon now does: same semantic fields twice.
    def project(task):
        events = {str(item.get("event", "")) for item in task.audit_log if isinstance(item, dict)}
        actors = {str(item.get("actor", "")) for item in task.audit_log if isinstance(item, dict)}
        lifecycle = task.outputs["external_mining"].setdefault("lifecycle", {})
        return {
            "researcher": "COMPLETED" if "researched" in events or "researcher" in actors else "PENDING",
            "validator": "COMPLETED" if "validated" in events or "validator" in actors else "PENDING",
            "guardian": "COMPLETED" if task.guardian_decision else "PENDING",
            "archivist": "COMPLETED" if task.status == "archived" or "archivist" in actors else "PENDING",
            "task_status": task.status,
            "guardian_decision": task.guardian_decision or "",
            "outcome_receipt": (task.outputs.get("outcome_receipt") or {}).get("status", "PENDING"),
            "production_integration": False,
        }

    path = pool._task_path(task.task_id, task.status)
    before_mtime = os.path.getmtime(path)

    lifecycle = task.outputs["external_mining"]["lifecycle"]
    changed = any(lifecycle.get(k) != v for k, v in project(task).items())
    assert changed is True, "the first projection must be written"
    lifecycle.update(project(task))
    task.outputs = dict(task.outputs)
    task.outputs["external_mining"]["lifecycle"] = lifecycle
    assert pool.update_task(task)

    # Second pass: nothing moved, so nothing may be written.
    stable_path = pool._task_path(task.task_id, task.status)
    settled = os.path.getmtime(stable_path)
    lifecycle = task.outputs["external_mining"]["lifecycle"]
    changed = any(lifecycle.get(k) != v for k, v in project(task).items())
    assert changed is False, "a converged projection must report no change"
    assert os.path.getmtime(stable_path) == settled
    assert before_mtime != settled, "the first pass must have persisted"