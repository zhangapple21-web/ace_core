"""Live-call execution tests: the system places the call the task waited for."""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.autonomous_adjudication as adj  # noqa: E402
from ops.test_support_lanes import seed_owners_table  # noqa: E402
from ops.test_autonomous_adjudication import (  # noqa: E402
    BLOCKED_REASON,
    ScriptedPool,
)

from core.task import TaskPool  # noqa: E402


def _live_call_fixture(root, task_id="RQ-LIVE-1", with_receipt=False):
    pool = TaskPool(str(root / "task_pool"))
    admission = {
        "source_type": "evidence", "source_ref": f"fixture:{task_id}",
        "why_now": "live-call fixture",
        "evidence": [{"source": "test", "content": "x"}],
        "expected_result": "a real model call",
        "verification_method": "assert the receipt",
        "risk": "low", "estimated_scope": "small",
    }
    created = pool.create_task(
        title="免费通道实弹验证：生产池经CLI双胞胎完成一次思考",
        creator="steward", priority="high", admission=admission,
        hypothesis="通道armed但零实战；需要一次生产池真调用",
        outputs={"terminal_disposition": "",
                 **({"model_execution": {"provider": "opencode_cli"}}
                    if with_receipt else {})},
    )
    stored = pool.load_task(created.task_id)
    stored.blocked_reason = BLOCKED_REASON
    stored.block_type = "manual_gate_blocked"
    stored.unchanged_review_count = 4
    stored.review_count = 5
    stored.evidence = []
    assert pool.update_task(stored)
    blocked = pool.block_task(created.task_id, BLOCKED_REASON,
                              actor="fixture", block_type="manual_gate_blocked")
    assert blocked is not None
    return created.task_id


def test_a_task_waiting_on_a_live_call_gets_one(tmp_path):
    seed_owners_table(tmp_path)
    tid = _live_call_fixture(tmp_path)
    pool = ScriptedPool(replies=["one short sentence"])
    state: dict = {}
    result = adj.adjudicate_task(tid, pool, tmp_path, state, max_tokens=32)
    assert result["action"] == "EXECUTE_LIVE_CALL", result
    assert pool.calls, "the call must actually be placed"
    assert result["receipt"].startswith("ADJ-LIVE-")

    reloaded = TaskPool(str(tmp_path / "task_pool")).load_task(tid)
    assert reloaded.status == "pending", "the task re-enters the loop with its receipt"
    assert any("live verification call" in str(e.get("content", "")).lower()
               for e in (reloaded.evidence or []))


def test_a_task_that_already_called_does_not_call_again(tmp_path):
    seed_owners_table(tmp_path)
    tid = _live_call_fixture(tmp_path, with_receipt=True)
    pool = ScriptedPool(replies=["one short sentence"])
    result = adj.adjudicate_task(tid, pool, tmp_path, {}, max_tokens=32)
    assert result["action"] != "EXECUTE_LIVE_CALL", (
        "a task with a receipt must not spend another live call")
    assert "receipt" not in result or not str(result.get("receipt", "")).startswith("ADJ-LIVE-")


def test_an_unavailable_live_call_seat_holds_without_forcing(tmp_path):
    seed_owners_table(tmp_path)
    tid = _live_call_fixture(tmp_path)
    pool = ScriptedPool(replies=[])
    result = adj.adjudicate_task(tid, pool, tmp_path, {}, max_tokens=32)
    assert result["action"] == "HOLD"
    assert "unavailable" in result["reason"] or "nothing" in result["reason"]
    assert TaskPool(str(tmp_path / "task_pool")).load_task(tid).status == "blocked"


def test_live_call_receipt_is_hash_bound_and_authorized(tmp_path):
    seed_owners_table(tmp_path)
    tid = _live_call_fixture(tmp_path)
    pool = ScriptedPool(replies=["one short sentence"])
    result = adj.adjudicate_task(tid, pool, tmp_path, {}, max_tokens=32)
    receipts = list((tmp_path / "08_GOVERNANCE" / "autonomous_adjudication"
                     / "receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["receipt_hash"]
    assert "no human in the loop" in receipt["authorization"]
    assert receipt["content_sha256"]
