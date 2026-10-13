"""The admissibility gate must refuse, and must say why.

A gate that unlocks everything is decoration. This one holds 68 of 68 today, so
its value is entirely in the named reasons - and in the specific refusals that
came out of getting it wrong first: the first version admitted a task whose
evidence was Telegram sales copy, because its mechanical checks (distinct
sources, non-duplicate entries) could not see that the material was unrelated to
the claim. The reader had written that fact down, so the gate was taught to read
what the reader wrote rather than to overrule it.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import ops.external_evidence_gate as gate  # noqa: E402

REQUIRED = gate.REQUIRED_SUPPORTED


def _review_file(root, sweep, tasks, entries):
    directory = root / "07_SANDBOX" / "free_research" / "reports" / "external_review"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"tasks": tasks, "reviews": entries, "contract_version": "x"}
    (directory / f"EXP-EXTREVIEW-{sweep}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _entry(reviewer, verdict, status="REVIEWED", detail=""):
    return {"reviewer": reviewer, "status": status, "detail": detail or f"VERDICT: {verdict}"}


def _task(root, task_id, evidence=None, unchanged=4, review=5,
          reason="相同证据集重复验证达到上限，等待人工或外部新证据"):
    blocked = root / "task_pool" / "blocked"
    blocked.mkdir(parents=True, exist_ok=True)
    task = {
        "task_id": task_id, "title": task_id, "status": "blocked",
        "blocked_reason": reason, "block_type": "manual_gate_blocked",
        "unchanged_review_count": unchanged, "review_count": review,
        "evidence": evidence if evidence is not None else [
            {"source": "runtime_observation:OBS-1", "content": "patrol returned error"},
            {"source": "runtime_observation:OBS-1", "content": "patrol returned error"},
        ],
    }
    (blocked / f"{task_id}.json").write_text(
        json.dumps(task, ensure_ascii=False), encoding="utf-8")
    return task


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "BASE_DIR", tmp_path)
    return tmp_path


# ------------------------------------------------------------------- refusals

def test_a_task_at_the_convergence_ceiling_is_held(tmp_path, workspace):
    """Reopening a task that already ran out of research room replays a loop.

    44 sibling tasks of the same shape sit in the blocked pool with
    unchanged_review_count == 4, the ceiling, so this is measured not assumed.
    """
    _task(workspace, "RQ-CEILING-1")
    report = gate.run(workspace)
    result = report["results"][0]
    assert result["admissible"] is False
    assert any("convergence ceiling" in r for r in result["reasons"])


def test_a_fresh_task_at_the_ceiling_is_held_even_with_support(tmp_path, workspace):
    """Support does not buy a reopen that cannot converge."""
    _task(workspace, "RQ-CEILING-2", unchanged=4, review=5)
    _review_file(workspace, "S1", ["RQ-CEILING-2"], [
        _entry("deepseek", "SUPPORTED"), _entry("gemma", "SUPPORTED")])
    result = gate.run(workspace)["results"][0]
    assert result["admissible"] is False
    assert any("convergence ceiling" in r for r in result["reasons"])


def test_a_reader_finding_insufficient_evidence_blocks_admission(tmp_path, workspace):
    """The Telegram-spam task.

    Its evidence is two distinct, non-duplicate files, so every mechanical check
    passed - and the material had nothing to do with the claim. The reader wrote
    that fact down, so the gate must read what the reader wrote instead of
    overruling it.
    """
    _task(workspace, "RQ-POLLUTED-1", unchanged=0, review=0, evidence=[
        {"source": "Telegram/百域量化.txt", "content": "接粉话术 开头一句"},
        {"source": "Telegram/三个问题.txt", "content": "为什么要用机构账户"},
    ])
    _review_file(workspace, "S1", ["RQ-POLLUTED-1"], [
        _entry("deepseek", "CANNOT_ASSESS",
               detail="The evidence has no connection to the claim. VERDICT: CANNOT_ASSESS"),
    ])
    result = gate.run(workspace)["results"][0]
    assert result["admissible"] is False
    assert any("evidence insufficient" in r for r in result["reasons"])


def test_a_task_with_no_review_coverage_is_held(tmp_path, workspace):
    _task(workspace, "RQ-NOCOVER-1", unchanged=0, review=0)
    result = gate.run(workspace)["results"][0]
    assert result["admissible"] is False
    assert any("no external review" in r for r in result["reasons"])


def test_a_contradicted_task_is_held_however_much_it_is_supported(tmp_path, workspace):
    _task(workspace, "RQ-AGAINST-1", unchanged=0, review=0)
    _review_file(workspace, "S1", ["RQ-AGAINST-1"], [
        _entry("deepseek", "SUPPORTED"),
        _entry("gemma", "SUPPORTED"),
        _entry("muse", "CONTRADICTED"),
    ])
    result = gate.run(workspace)["results"][0]
    assert result["admissible"] is False
    assert any("CONTRADICTED" in r for r in result["reasons"])


def test_duplicate_evidence_is_named(tmp_path, workspace):
    _task(workspace, "RQ-DUP-1", unchanged=0, review=0, evidence=[
        {"source": "obs:1", "content": "same"},
        {"source": "obs:1", "content": "same"},
        {"source": "obs:1", "content": "same"},
    ])
    result = gate.run(workspace)["results"][0]
    assert any("byte-identical" in r for r in result["reasons"])


def test_a_reviewer_repeating_itself_is_not_a_second_opinion(tmp_path, workspace):
    """Four sweeps, one reviewer saying SUPPORTED each time, is one opinion."""
    _task(workspace, "RQ-ECHO-1", unchanged=0, review=0)
    for index in range(1, 5):
        _review_file(workspace, f"S{index}", ["RQ-ECHO-1"],
                     [_entry("deepseek", "SUPPORTED")])
    result = gate.run(workspace)["results"][0]
    review = result["review"]
    assert review["supported"] == ["deepseek"], "a repeat is not corroboration"
    assert len(review["supported"]) < REQUIRED
    assert result["admissible"] is False


def test_a_task_that_meets_every_bar_is_admitted(tmp_path, workspace):
    """The gate can say yes - otherwise its no would be meaningless."""
    _task(workspace, "RQ-GOOD-1", unchanged=0, review=0, evidence=[
        {"source": "runtime_observation:OBS-A", "content": "first distinct observation"},
        {"source": "archivist:abc", "content": "second distinct independent record"},
    ])
    _review_file(workspace, "S1", ["RQ-GOOD-1"], [
        _entry("deepseek", "SUPPORTED"), _entry("gemma", "SUPPORTED")])
    result = gate.run(workspace)["results"][0]
    assert result["admissible"] is True
    assert result["reasons"] == []
    assert sorted(result["review"]["supported"]) == ["deepseek", "gemma"]


# ------------------------------------------------------------------- the live run

def test_the_live_pool_holds_with_named_reasons():
    """What "automated processing" actually found when applied for real.

    This asserts structure, not a snapshot: the pool grows as the lifecycle
    runs, so pinning an exact count would red on every new blocked task. What
    must never change is that every held task carries a stated reason, and that
    any admissible task meets the bar. (2026-10-13 run: 78 considered, 0
    admissible.)
    """
    report = gate.run(gate.BASE_DIR)
    assert report["tasks_considered"] > 0, "the gate must see the live pool"
    for result in report["results"]:
        if result["admissible"]:
            review = result["review"]
            assert len(review["supported"]) >= gate.REQUIRED_SUPPORTED
            assert not review["contradicted"]
            assert not review.get("evidence_flags"), (
                f"{result['task_id']} admitted despite a reader flagging its evidence"
            )
        else:
            assert result["reasons"], f"{result['task_id']} was held with no reason given"


def test_the_gate_is_read_only_over_the_task_pool():
    """It assesses; it never reopens. Unblocking is a separate audited step."""
    assert not hasattr(gate, "reopen_task")
    assert "reopen_task" not in dir(gate)