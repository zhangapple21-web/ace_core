# RQ-20261006-010 regression: an unmodified task must not be rewritten.
# Before the fix, AceDaemon called check_heat_upgrade(task) for the top-20
# reference-count tasks every cycle and update_task ran regardless of the
# return value, so _save_task -> touch() refreshed mtime/updated_at with no
# audit row and no ledger row. This test pins the gate.
import os

from core.task import TaskPool

ADMISSION = {
    "source_type": "maintenance",
    "source_ref": "ops/test_task_pool_heat_upgrade_idempotence.py",
    "why_now": "regression for RQ-20261006-010",
    "evidence": ["archived records were rewritten every cycle without any audit or ledger row"],
    "expected_result": "unmodified tasks are not rewritten; real upgrades still persist",
    "verification_method": "pytest",
    "risk": "low: test fixture",
    "estimated_scope": "single-test",
}


def test_check_heat_upgrade_does_not_persist_without_an_upgrade(tmp_path):
    pool = TaskPool(str(tmp_path))
    task = pool.create_task(title="heat probe", hypothesis="probe", admission=dict(ADMISSION))
    path = pool._task_path(task.task_id, task.status)
    assert path.exists()
    before_mtime = os.path.getmtime(path)
    before_updated_at = task.updated_at
    for _ in range(3):
        assert pool.check_heat_upgrade(task) is False
    assert os.path.getmtime(path) == before_mtime, "unmodified task file was rewritten"
    assert task.updated_at == before_updated_at, "updated_at moved without a change"


def test_check_heat_upgrade_still_persists_a_real_upgrade(tmp_path):
    pool = TaskPool(str(tmp_path))
    task = pool.create_task(
        title="heat probe",
        priority="low",
        hypothesis="probe",
        admission={**ADMISSION, "why_now": "regression for RQ-20261006-010 (upgrade path)"},
    )
    task.reference_count = 3
    path = pool._task_path(task.task_id, task.status)
    before_mtime = os.path.getmtime(path)
    assert pool.check_heat_upgrade(task) is True
    assert task.priority == "medium"
    assert os.path.getmtime(path) != before_mtime, "a real upgrade must persist"


def test_daemon_gates_persistence_behind_the_return_value():
    source = open("ace_daemon.py", encoding="utf-8").read()
    assert "if self.task_pool.check_heat_upgrade(task):" in source, (
        "daemon must gate persistence behind check_heat_upgrade's return value"
    )