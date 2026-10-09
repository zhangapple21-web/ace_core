# Regression: the patrol tells known governance backlog apart from real faults.
#
# Field evidence: all 62 blocked tasks on 2026-10-09 are terminal +
# manual_gate_blocked + the same governance-wait reason. Counting them as
# "failure" errored the patrol every hour and manufactured a task per
# cycle. The gate must error only on genuinely abnormal blocks while the
# known backlog stays visible as inventory with counts and reasons.
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _blocked_task(task_id, terminal, reason, age_hours, owner=""):
    return {
        "task_id": task_id,
        "status": "blocked",
        "block_type": "manual_gate_blocked",
        "blocked_reason": reason,
        "lease_owner": owner,
        "claim_id": "",
        "updated_at": (datetime.now() - timedelta(hours=age_hours)).isoformat(),
        "outputs": {
            "terminal_non_convergent": terminal,
            "rework_reason": reason,
        },
    }


GOV_REASON = "相同证据集重复验证达到上限，等待人工或外部新证据"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    from ops import health_check

    monkeypatch.setattr(health_check, "BASE_DIR", Path(tmp_path))
    pool = Path(tmp_path) / "task_pool"
    (pool / "blocked").mkdir(parents=True)
    (pool / "active").mkdir(parents=True)
    (pool / "pending").mkdir(parents=True)
    return Path(tmp_path)


def _seed(workdir, tasks):
    blocked = workdir / "task_pool" / "blocked"
    for task in tasks:
        (blocked / f"{task['task_id']}.json").write_text(
            json.dumps(task, ensure_ascii=False), encoding="utf-8"
        )


def _triage(workdir):
    from ops import health_check

    checker = health_check.HealthChecker()
    checker._check_task_pool()
    return checker


def _entry(checker, name):
    for entry in checker.results:
        if entry["name"] == name:
            return entry
    raise AssertionError(f"check {name!r} missing")


def test_known_governance_backlog_passes_but_stays_visible(workdir):
    _seed(workdir, [
        _blocked_task("RQ-20261009-019", True, GOV_REASON, 1),
        _blocked_task("RQ-20261008-002", True, GOV_REASON, 400),
        _blocked_task("RQ-20260912-002", True, GOV_REASON, 648),
    ])
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is True
    assert "abnormal=0" in gate["detail"]
    assert "known_governance=3" in gate["detail"]
    assert not checker.errors

    inventory = _entry(checker, "已知治理阻塞登记")
    assert inventory["passed"] is False
    assert inventory["severity"] == "warning"
    assert "3 known_governance" in inventory["detail"]


def test_abnormal_error_reason_errors_even_when_fresh(workdir):
    _seed(workdir, [
        _blocked_task("RQ-20261009-019", True, GOV_REASON, 1),
        {
            **_blocked_task("RQ-20261009-099", False, "connection timeout after 3 retries", 1),
            "outputs": {"terminal_non_convergent": False},
        },
    ])
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is False
    assert gate["severity"] == "error"
    assert "abnormal=1" in gate["detail"]
    assert "RQ-20261009-099" in gate["detail"]
    assert checker.errors


def test_orphaned_block_names_itself(workdir):
    task = _blocked_task("RQ-20261001-001", False, "等待补充研究", 240)
    task["outputs"] = {"terminal_non_convergent": False}
    _seed(workdir, [task])
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is False
    assert "abnormal=1" in gate["detail"]
    assert "orphaned" in gate["detail"]


def test_fresh_transitional_block_is_not_abnormal(workdir):
    # Mid-lifecycle, recently touched, no owner between cycles: normal.
    task = _blocked_task("RQ-20261009-100", False, "验证员要求补充研究", 1)
    task["outputs"] = {"terminal_non_convergent": False}
    _seed(workdir, [task])
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is True
    assert "unclassified=1" in gate["detail"]
    assert not checker.errors


def test_empty_pool_passes_silently(workdir):
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is True
    assert not checker.errors
    assert [e for e in checker.results if e["name"] == "已知治理阻塞登记"] == []


def test_unreadable_task_file_is_abnormal(workdir):
    (workdir / "task_pool" / "blocked" / "RQ-20261009-101.json").write_text(
        '{"truncated', encoding="utf-8"
    )
    checker = _triage(workdir)

    gate = _entry(checker, "无大量阻塞任务")
    assert gate["passed"] is False
    assert "abnormal=1" in gate["detail"]
