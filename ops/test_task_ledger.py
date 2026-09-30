"""任务账本（C4）回归测试。

覆盖：旧数据兼容、入账来源、重放复算、未登记漂移检出、enforce 阻断、
活指针拒死链、hold/release 成对、篡改可发现。

跑法：
    cd C:/tmp/ace_core
    PYTHONIOENCODING=utf-8 py -3.11 -m pytest ops/test_task_ledger.py -q
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import task_ledger as ledger
from core.task import Task, TaskPool
from ops.test_support import FixtureTaskPool


LEGACY_RECORD = {
    "task_id": "RQ-20260101-900",
    "title": "legacy task without ledger",
    "creator": "test",
    "status": "pending",
    "priority": "medium",
    "hypothesis": "",
    "evidence": [],
    "counter_examples": [],
    "result": None,
    "tags": [],
    "references": [],
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-01T00:00:00",
    "last_referenced_at": "2026-01-01T00:00:00",
    "reference_count": 7,
    "assignee": None,
    "research_notes": [],
    "validation_notes": [],
    "guardian_decision": None,
    "review_count": 2,
    "depends_on": [],
    "blocked_reason": "",
    "parent_task": "",
    "outputs": {},
    "failure_reason": "",
    "retry_count": 3,
    "audit_log": [],
    "selection_trace": [],
    "recursion_depth": 0,
    "lease_owner": "",
    "lease_expires_at": "",
    "claim_id": "",
    "fencing_token": 5,
    "block_type": "",
    "retry_after": "",
    "rework_count": 1,
    "last_claimed_at": "",
    "unchanged_review_count": 0,
    "consecutive_rework_claims": 0,
    "starvation_age": 4,
}


def _load_record(pool_dir: Path, task_id: str) -> dict:
    matches = list(pool_dir.glob(f"*/{task_id}.json"))
    assert matches, f"no file for {task_id}"
    return json.loads(matches[0].read_text(encoding="utf-8"))


def test_legacy_task_loads_and_seeds_baseline_from_disk_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool_dir = Path(temp_dir)
        (pool_dir / "pending").mkdir(parents=True)
        (pool_dir / "pending" / f"{LEGACY_RECORD['task_id']}.json").write_text(
            json.dumps(LEGACY_RECORD, ensure_ascii=False), encoding="utf-8"
        )
        pool = FixtureTaskPool(str(pool_dir))
        task = pool.load_task(LEGACY_RECORD["task_id"])
        assert task is not None
        assert task.ledger == []          # 旧数据没有账本，装载不得报错
        assert pool.update_task(task)     # 首次落盘种基线

        record = _load_record(pool_dir, task.task_id)
        rows = record["ledger"]
        baseline = [row for row in rows if row["kind"] == "baseline"]
        assert len(baseline) == 1
        # 基线必须用落盘前的历史值，而不是就地伪造当前值
        assert baseline[0]["after"]["reference_count"] == 7
        assert baseline[0]["after"]["retry_count"] == 3
        assert baseline[0]["after"]["fencing_token"] == 5
        assert baseline[0]["reason"] == "pre_ledger_migration"
        assert baseline[0]["ref"]["type"] == "task"
        assert baseline[0]["ref"]["task_id"] == task.task_id
        assert Path(baseline[0]["ref"]["file"]).name == f"{task.task_id}.json"
        assert ledger.reconcile(pool.load_task(task.task_id)) == {}


def test_claim_records_hold_with_fencing_provenance():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = FixtureTaskPool(temp_dir)
        task = pool.create_task("ledger probe")
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        assert claimed is not None
        record = _load_record(Path(temp_dir), task.task_id)
        holds = [row for row in record["ledger"] if row["kind"] == "hold"]
        assert len(holds) == 1
        assert holds[0]["deltas"]["fencing_token"] == 1
        assert holds[0]["ref"]["claim_id"] == record["claim_id"]
        assert holds[0]["after"]["fencing_token"] == record["fencing_token"]
        assert ledger.verify_chain(pool.load_task(task.task_id)) == []


def test_fail_records_retry_and_releases_hold():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = FixtureTaskPool(temp_dir)
        task = pool.create_task("ledger probe fail")
        pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        failed = pool.fail_task(task.task_id, "boom", actor="researcher")
        assert failed is not None
        record = _load_record(Path(temp_dir), task.task_id)
        rows = record["ledger"]
        consumes = [row for row in rows if row["kind"] == "consume"]
        assert consumes and consumes[-1]["deltas"]["retry_count"] == 1
        assert consumes[-1]["reason"] == "failure:retryable"
        assert [row for row in rows if row["kind"] == "release"]
        reloaded = pool.load_task(task.task_id)
        assert ledger.unclosed_holds(reloaded) == []
        assert ledger.reconcile(reloaded) == {}


def test_unregistered_counter_change_becomes_drift_row(monkeypatch):
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "shadow")
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = FixtureTaskPool(temp_dir)
        task = pool.create_task("drift probe")
        pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        loaded = pool.load_task(task.task_id)
        loaded.starvation_age += 3            # 没人登记来源的改动
        assert pool.update_task(loaded)
        record = _load_record(Path(temp_dir), task.task_id)
        drift = [row for row in record["ledger"] if row["kind"] == "drift"]
        assert drift and drift[-1]["deltas"]["starvation_age"] == 3
        assert drift[-1]["reason"] == "unregistered_counter_change"
        # shadow 模式必须让账本重新自洽
        assert ledger.reconcile(pool.load_task(task.task_id)) == {}


def test_enforce_mode_blocks_unregistered_change(monkeypatch):
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = FixtureTaskPool(temp_dir)
        task = pool.create_task("enforce probe")
        pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        before = _load_record(Path(temp_dir), task.task_id)
        loaded = pool.load_task(task.task_id)
        loaded.rework_count += 2
        raised = False
        try:
            pool.update_task(loaded)
        except ledger.LedgerDriftError as error:
            raised = True
            assert "rework_count" in str(error)
        assert raised
        assert _load_record(Path(temp_dir), task.task_id) == before   # 未落盘


def test_dead_pointer_ref_is_rejected():
    task = Task("RQ-20260101-901", "ref probe")
    task.retry_count = 1
    try:
        ledger.ensure_baseline(task, Path("C:/tmp/nonexistent-pool/RQ-20260101-901.json"))
        ledger.append_entry(
            task,
            kind="consume",
            actor="test",
            deltas={"retry_count": 1},
            reason="should not land",
            ref={"type": "file", "path": "C:/tmp/definitely-absent-file-9f3a.md"},
        )
    except ledger.LedgerError as error:
        assert "ledger_ref_dead" in str(error)
    else:
        raise AssertionError("dead pointer accepted")
    assert len(task.ledger) == 1     # 只有基线行，死链行没进账


def test_line_pointer_must_be_in_range():
    with tempfile.TemporaryDirectory() as temp_dir:
        probe = Path(temp_dir) / "probe.md"
        probe.write_text("one\n two\n three\n", encoding="utf-8")
        ok, _ = ledger.resolve_ref({"type": "line", "path": str(probe), "line": 3})
        assert ok
        ok, error = ledger.resolve_ref({"type": "line", "path": str(probe), "line": 99})
        assert not ok and "out_of_range" in error


def test_replay_reproduces_every_counter_and_flags_chain_break():
    task = Task("RQ-20260101-902", "replay probe", retry_count=0, fencing_token=0)
    path = Path("C:/tmp/replay-probe.json")
    ledger.ensure_baseline(task, path)
    task.retry_count += 1
    ledger.append_entry(task, "consume", "test", {"retry_count": 1}, "first retry", {"type": "self", "task_id": task.task_id})
    task.fencing_token += 1
    ledger.append_entry(task, "hold", "test", {"fencing_token": 1}, "claimed", {"type": "self", "task_id": task.task_id})
    assert ledger.replay(task)["retry_count"] == 1
    assert ledger.reconcile(task) == {}
    assert ledger.verify_chain(task) == []
    task.ledger[-2]["after"]["retry_count"] = 42      # 篡改 consume 行快照
    broken = ledger.verify_chain(task)
    assert broken and broken[0]["counter"] == "retry_count"


def test_ledger_roundtrips_through_to_dict():
    task = Task("RQ-20260101-903", "roundtrip", ledger=[{"entry_id": 1, "kind": "baseline"}], ledger_seq=1)
    clone = Task.from_dict(task.to_dict())
    assert clone.ledger == task.ledger
    assert clone.ledger_seq == 1


def test_mode_off_disables_the_gate(monkeypatch):
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "off")
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = FixtureTaskPool(temp_dir)
        task = pool.create_task("off probe")
        record = _load_record(Path(temp_dir), task.task_id)
        assert record["ledger"] == []
