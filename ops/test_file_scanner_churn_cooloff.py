# Regression: churning runtime state must cool off instead of refiling.
#
# Field evidence: C:\tmp\ace_codex_guard\state.json was filed 141 times
# because it mutates constantly, and each filing burned four validator
# reviews before parking terminally blocked. ChatExport and evidence_graph
# families show the same shape. A path with three recent terminal strikes
# and no approval cools off for thirty days instead of filing again.
import json
from pathlib import Path

from core.file_scanner import FileScanner
from core.fragment_index import FragmentIndex
from core.task import TaskPool

ADMISSION = {
    "source_type": "maintenance",
    "source_ref": "ops/test_file_scanner_churn_cooloff.py",
    "why_now": "regression for churn refiling waste",
    "evidence": ["state.json filed 141 times, each burning four reviews"],
    "expected_result": "churning paths cool off; fresh and approved paths file",
    "verification_method": "pytest",
    "risk": "low: test fixtures in tmp_path",
    "estimated_scope": "single-test",
}


def _stack(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    index = FragmentIndex(str(tmp_path / "elsewhere" / "index"))
    scan_root = tmp_path / "scan"
    scan_root.mkdir(parents=True, exist_ok=True)
    return FileScanner(pool, index, [scan_root]), pool


def _terminal_task(pool, source_file, seq):
    # Blocked is terminal for these tasks: blocked has no outgoing edge to
    # archived (ALLOWED_TRANSITIONS), so terminal records live in blocked/.
    # The cool-off must count them where they actually are.
    #
    # Each strike needs a genuinely distinct admission envelope, or
    # create_task folds it into the existing same-intent task and only one
    # record survives. Field evidence for how real churn escapes dedup:
    # the 141 state.json filings each carried source_ref
    # "<path>:<mtime>:<size>", a different locator per strike.
    admission = dict(ADMISSION)
    admission["source_ref"] = f"{source_file}:2026-10-0{seq}T00:00:00:{100 + seq}"
    task = pool.create_task(
        title=f"churn probe {seq}",
        hypothesis="h",
        admission=admission,
    )
    assert task.outputs["admission"]["source_ref"] == admission["source_ref"], \
        "the strike was folded into an existing task; the fixture proves nothing"
    pool.block_task(task.task_id, "waiting on evidence", actor="test")
    stored = pool.load_task(task.task_id)
    stored.outputs["terminal_non_convergent"] = True
    stored.outputs["source_file"] = source_file
    assert pool.update_task(stored)
    return task


def test_three_terminal_strikes_cool_off(tmp_path):
    scanner, pool = _stack(tmp_path)
    target = tmp_path / "scan" / "state.json"
    target.write_text('{"tick": 1}', encoding="utf-8")
    resolved = str(target.resolve())
    for seq in range(1, 4):
        _terminal_task(pool, resolved, seq)

    result = scanner.scan_and_create(max_new=3)

    assert result["tasks_created"] == 0
    assert result.get("churn_cooled", 0) == 1
    assert pool.get_stats()["total"] == 3, "no fourth task may be filed"


def test_approved_path_is_never_churn(tmp_path):
    scanner, pool = _stack(tmp_path)
    target = tmp_path / "scan" / "good.md"
    target.write_text(
        "# Real finding\nThe gateway route falls back across providers.\nHealth scores decay without refresh.\nAdmission needs two evidence groups.\n",
        encoding="utf-8",
    )
    resolved = str(target.resolve())
    for seq in range(1, 6):
        _terminal_task(pool, resolved, seq)
    good = pool.create_task(
        title="good one", hypothesis="h", admission=dict(ADMISSION)
    )
    good.outputs["source_file"] = resolved
    assert pool.update_task(good)
    # pending -> review is not an allowed edge (ALLOWED_TRANSITIONS); an
    # unasserted move_task silently returns None and the task stays pending,
    # which would leave the approval this test relies on unproven.
    assert pool.move_task(good.task_id, "active", actor="test", reason="claimed")
    assert pool.move_task(good.task_id, "review", actor="test", reason="review")
    assert pool.move_task(good.task_id, "approved", actor="test", reason="approved work")
    assert pool.move_task(good.task_id, "archived", actor="test", reason="archived")
    assert pool.load_task(good.task_id).status == "archived"

    result = scanner.scan_and_create(max_new=3)

    assert result["tasks_created"] == 1, "an approved path must always file"


def test_old_spree_does_not_silence_forever(tmp_path, monkeypatch):
    scanner, pool = _stack(tmp_path)
    target = tmp_path / "scan" / "old.md"
    target.write_text('{"tick": 1}', encoding="utf-8")
    resolved = str(target.resolve())
    for seq in range(1, 4):
        _terminal_task(pool, resolved, seq)

    assert scanner._in_churn_cooloff(target) is True
    monkeypatch.setattr(scanner, "CHURN_COOLOFF_DAYS", 0)
    assert scanner._in_churn_cooloff(target) is False
