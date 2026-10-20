"""Autonomous adjudication: the system rules, and the rules are what act.

What these tests defend, in order of importance:

1. Models advise; deterministic code decides. _decide takes a deliberation and
   returns an action - no model output ever flows directly into a TaskPool call.
2. Convergence is provider independence plus citations, never volume. Two seats
   on one vendor agreeing is one failure mode agreeing with itself.
3. Model prose never enters a task as evidence. Transcripts live in receipt
   files and are quoted in research notes as readings ("seat X said ...").
   Only performed-check receipts - observations of actions really taken - may
   enter as evidence.
4. The paid seat is budgeted. Free labor first; paid thinks only on demand and
   inside a daily cap.
5. Every ruling carries the authorization it ran under, or it did not happen.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import core.autonomous_adjudication as adj  # noqa: E402

BLOCKED_REASON = "相同证据集重复验证达到上限，等待人工或外部新证据"


class ScriptedPool:
    """Answers queued replies; records how it was asked."""

    def __init__(self, replies=None):
        self._replies = list(replies or [])
        self.calls = []

    def chat(self, task_type="", messages=None, system_prompt="",
             selected_spec=None, max_retries=1, max_tokens=0,
             data_boundary=None, **kwargs):
        self.calls.append({
            "model": getattr(selected_spec, "full_id", str(selected_spec)),
            "provider": getattr(selected_spec, "provider", "?"),
            "retries": max_retries,
            "boundary": data_boundary,
        })
        reply = self._replies.pop(0) if self._replies else ""
        ok = bool(reply)
        return {"success": ok, "content": reply, "error": "" if ok else "empty",
                "provider": getattr(selected_spec, "provider", "?"),
                "model": getattr(selected_spec, "model", "?")}


def _verdict(seat, verdict, record="RQ-20261008-007"):
    return {"seat": seat, "status": "SPOKEN", "round": 1,
            "provider": seat.split(":")[0],
            "text": f"POSITION: {verdict.lower()} the task.\n"
                    f"EVIDENCE: {record} archive shows it.\n"
                    f"VERDICT: {verdict}"}


# ------------------------------------------------------------------ rostering

def test_roster_spans_two_providers_and_rotates_by_task():
    first, _ = adj.roster_seats(None, need_paid=False, state={}, task_id="RQ-A")
    second, _ = adj.roster_seats(None, need_paid=False, state={}, task_id="RQ-B")
    assert len(first) == 3
    assert len({s.split(":")[0] for s in first}) >= 2, "one vendor is an echo chamber"
    # rotation means different tasks do not always get the same trio
    rosters = {tuple(sorted(adj.roster_seats(None, need_paid=False, state={}, task_id=f"RQ-{i}")[0]))
               for i in range(6)}
    assert len(rosters) > 1


def test_paid_seat_joins_only_on_demand_and_inside_its_cap():
    seats, seating = adj.roster_seats(None, need_paid=False, state={})
    assert not seating["paid"]["used"]
    assert all(not s.startswith("shenwen") for s in seats)

    seats, seating = adj.roster_seats(None, need_paid=True, state={})
    assert seating["paid"]["used"]
    assert seats[-1] == adj.PAID_SEAT

    from datetime import date
    spent = adj.PAID_DAILY_CAP
    seats, seating = adj.roster_seats(
        None, need_paid=True, state={"paid_spend": {date.today().isoformat(): spent}})
    assert not seating["paid"]["used"], "the daily cap is a cap, not a suggestion"
    assert all(not s.startswith("shenwen") for s in seats)
    assert "cap" in seating["paid"]["reason"]


def test_rostered_calls_are_pinned_public_and_single_attempt():
    pool = ScriptedPool(replies=["x"] * 12)
    packet = {"task_id": "RQ-X", "title": "t", "hypothesis": "h",
              "evidence": [], "reviews": []}
    adj.deliberate(packet, ["opencode_cli:muse-spark-1.3-contributor-free",
                            "amd_radeon:DeepSeek-V4-Flash"], pool, max_tokens=64)
    assert pool.calls
    for call in pool.calls:
        assert call["retries"] == 1
        assert call["boundary"] == {"data_class": "PUBLIC"}


# ------------------------------------------------------------------ aggregation

def test_two_providers_agreeing_with_citations_converges():
    transcript = [
        _verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"),
        _verdict("amd_radeon:DeepSeek-V4-Flash", "CLOSE"),
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["converged"] is True
    assert aggregation["ruling"] == "CLOSE"


def test_two_seats_on_one_vendor_agreeing_does_not_converge():
    """Two voices on one vendor failing together is not independence."""
    transcript = [
        _verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"),
        _verdict("opencode_cli:mimo-v2.6-flash-free", "CLOSE"),
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["converged"] is False
    assert aggregation["ruling"] is None


def test_one_disagreement_blocks_convergence():
    transcript = [
        _verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"),
        _verdict("amd_radeon:DeepSeek-V4-Flash", "CLOSE"),
        _verdict("amd_radeon:MiniCPM5-2B", "PROCEED"),
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["converged"] is False


def test_agreement_without_a_cited_record_does_not_converge():
    transcript = [
        {"seat": "opencode_cli:muse-spark-1.3-contributor-free", "status": "SPOKEN",
         "round": 1, "provider": "opencode_cli",
         "text": "POSITION: close it.\nEVIDENCE: trust me.\nVERDICT: CLOSE"},
        {"seat": "amd_radeon:DeepSeek-V4-Flash", "status": "SPOKEN",
         "round": 1, "provider": "amd_radeon",
         "text": "POSITION: close it.\nEVIDENCE: feels right.\nVERDICT: CLOSE"},
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["converged"] is False, "citations are required, not optional"


def test_a_repeating_seat_is_one_voice():
    transcript = [
        _verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"),
        dict(_verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"), round=2),
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["seats_heard"] == 1
    assert aggregation["converged"] is False


def test_silence_is_not_consent():
    transcript = [
        _verdict("opencode_cli:muse-spark-1.3-contributor-free", "CLOSE"),
        {"seat": "amd_radeon:DeepSeek-V4-Flash", "status": "UNAVAILABLE", "round": 1},
    ]
    aggregation = adj.aggregate(transcript)
    assert aggregation["converged"] is False


# ------------------------------------------------------------------ performed checks

def test_a_workspace_file_check_is_performed_with_a_receipt(tmp_path):
    target = tmp_path / "notes.md"
    target.write_text("gateway log: 403 key-disabled", encoding="utf-8")
    pool = ScriptedPool()
    receipt = adj.perform_check("read notes.md and confirm the 403", tmp_path, pool)
    assert receipt["status"] == "PERFORMED"
    assert receipt["action"] == "read_file"
    assert receipt["sha256"] and receipt["excerpt"]
    assert not pool.calls, "a file read must not spend a model call"


def test_a_check_escaping_the_workspace_is_refused(tmp_path):
    receipt = adj.perform_check("read ../../etc/passwd for the key", tmp_path, ScriptedPool())
    assert receipt["status"] == "REFUSED"
    assert "escapes" in receipt["reason"]


def test_an_unactionable_check_is_refused_not_improvised(tmp_path):
    receipt = adj.perform_check("rotate the upstream API key", tmp_path, ScriptedPool())
    assert receipt["status"] == "REFUSED"


def test_a_model_call_check_is_refused_by_the_check_runner(tmp_path):
    """Model calls run through the execution action with their own accounting."""
    receipt = adj.perform_check("place a live call to verify the channel", tmp_path, ScriptedPool())
    assert receipt["status"] == "REFUSED"


# ------------------------------------------------------------------ decide + apply

def _blocked_fixture(root, task_id="RQ-ADJ-1"):
    from core.task import TaskPool

    pool = TaskPool(str(root / "task_pool"))
    admission = {
        "source_type": "evidence", "source_ref": f"fixture:{task_id}",
        "why_now": "adjudication fixture",
        "evidence": [{"source": "test", "content": "x"}],
        "expected_result": "a ruling with a receipt",
        "verification_method": "assert the state and the receipt",
        "risk": "low", "estimated_scope": "small",
    }
    created = pool.create_task(title=f"stuck {task_id}", creator="observation_to_task",
                               priority="high", admission=admission,
                               outputs={"terminal_disposition": ""})
    stored = pool.load_task(created.task_id)
    stored.blocked_reason = BLOCKED_REASON
    stored.block_type = "manual_gate_blocked"
    stored.unchanged_review_count = 4
    stored.review_count = 5
    stored.evidence = [{"source": "obs:1", "content": "patrol error"}]
    assert pool.update_task(stored)
    blocked = pool.block_task(created.task_id, BLOCKED_REASON,
                              actor="fixture", block_type="manual_gate_blocked")
    assert blocked is not None
    return created.task_id


def test_execute_path_reopens_with_performed_receipts_as_evidence(tmp_path):
    tid = _blocked_fixture(tmp_path)
    performed = [{"status": "PERFORMED", "action": "read_file",
                  "check": "read gateway.log", "target": "gateway.log",
                  "sha256": "abc123", "excerpt": "403 key-disabled at 20:02"}]
    from core.task import TaskPool

    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.load_task(tid)
    action, detail = adj._decide(task, {}, performed, performed, None, 0)
    assert action == "EXECUTE"

    receipt = {"receipt_id": "ADJ-TEST", "receipt_hash": "h"}
    adj._apply(pool, task, action, detail, performed, None, receipt, None)
    reloaded = pool.load_task(tid)
    assert reloaded.status == "pending", "reopen must move blocked->pending"
    assert any("autonomous_adjudication" in str(e.get("actor", ""))
               for e in (reloaded.audit_log or [])), "the ruling must be in the audit trail"
    assert any("403 key-disabled" in str(e.get("content", ""))
               for e in (reloaded.evidence or [])), "a performed observation may enter as evidence"


def test_deliberation_prose_enters_notes_never_evidence(tmp_path):
    tid = _blocked_fixture(tmp_path)
    from core.task import TaskPool

    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.load_task(tid)
    before = len(task.evidence or [])
    deliberation = {"transcript": [
        {"seat": "opencode_cli:muse", "status": "SPOKEN", "round": 1,
         "text": "POSITION: close it.\nEVIDENCE: RQ-X.\nVERDICT: CLOSE"},
    ], "aggregation": {"converged": False}}
    adj._note(task, pool, deliberation, {"receipt_id": "ADJ-TEST"})
    reloaded = pool.load_task(tid)
    assert len(reloaded.evidence or []) == before, "model prose must never become evidence"
    assert any("seat opencode_cli:muse said:" in str(n.get("content", ""))
               for n in (reloaded.research_notes or [])), "but it must be quoted as a reading"


def test_hold_after_exhausted_deliberations_names_it(tmp_path):
    tid = _blocked_fixture(tmp_path)
    from core.task import TaskPool

    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.load_task(tid)
    action, detail = adj._decide(task, {}, [], [],
                                 {"aggregation": {"converged": False}},
                                 adj.MAX_DELIBERATIONS_PER_TASK)
    assert action == "HOLD"
    assert "exhausted" in detail or "budget" in detail


def test_every_receipt_carries_the_authorization():
    assert "no human in the loop" in adj.AUTHORIZATION
    assert "batch force-unlocks" in adj.AUTHORIZATION or "force-unlock" in adj.AUTHORIZATION


def test_run_cycle_respects_cooldown_and_empty_pool(tmp_path):
    (tmp_path / "task_pool").mkdir(parents=True, exist_ok=True)
    report = adj.run_cycle(tmp_path, ScriptedPool())
    assert report["status"] == "NOTHING_DUE"
    # write a fresh state with a recent cycle: cooldown must hold
    import json
    from datetime import datetime, timezone
    state_path = tmp_path / "07_SANDBOX" / "free_research" / "adjudication_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(
        {"last_cycle_at": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
    report = adj.run_cycle(tmp_path, ScriptedPool())
    assert report["status"] == "NOT_DUE"
    assert "cooldown" in report["reason"]
