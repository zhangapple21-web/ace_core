"""ace_start now carries both axes: the task claim and the file-region claim.

The gap it closes: a window could start a task through the sole sanctioned
entrypoint while another window edited the same source file, because
TaskPool claims tasks and nothing claimed files. These tests pin that a refused
lane claim fails the start, and that a start with no declared region still works
exactly as before.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.ace_start import ace_start  # noqa: E402


@pytest.fixture()
def workspace(tmp_path):
    """A pool with one active task, plus a lane registry over the same root."""
    from core.task import TaskPool
    from core.window_lane import LaneRegistry

    owners = {"regions": {}, "shared": []}
    LaneRegistry(tmp_path, owners_table=owners, state_path=tmp_path / "claims.json")
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task(
        "lane integration fixture",
        creator="ace_start",
        priority="high",
        admission={
            "source_type": "evidence", "source_ref": "fixture:lane-integration",
            "why_now": "prove start carries both axes",
            "evidence": [{"source": "test", "content": "fixture"}],
            "expected_result": "a task claim plus a lane claim, or a refusal",
            "verification_method": "assert both results",
            "risk": "low", "estimated_scope": "small",
        },
        outputs={"execution_discipline": {}},
    )
    return tmp_path, pool


def _pool_for(root):
    from core.task import TaskPool
    return TaskPool(str(root / "task_pool"))


def _first_task(pool):
    return pool.list_tasks(limit=10, sort_by="created")[0]


def test_a_start_without_regions_behaves_exactly_as_before(workspace):
    root, pool = workspace
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "window-a", 300)
    assert result["status"] == "STARTED"
    assert result["claim_id"]
    assert result["lane_claims"] == []


def test_a_start_with_regions_claims_them(workspace):
    root, pool = workspace
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "window-a", 300,
                       regions=["core/lane_a.py"], base_dir=str(root))
    assert result["status"] == "STARTED"
    assert len(result["lane_claims"]) == 1
    assert result["lane_claims"][0]["region"] == "core/lane_a.py"
    assert result["lane_claims"][0]["lane"] == "window-a"


def test_a_refused_lane_claim_fails_the_start(workspace):
    root, pool = workspace
    task = _first_task(pool)
    first = ace_start(pool, task.task_id, "window-a", 300,
                      regions=["core/lane_a.py"], base_dir=str(root))
    assert first["status"] == "STARTED"

    from core.task import TaskPool

    pool2 = TaskPool(str(root / "task_pool"))
    task2 = pool2.create_task(
        "second lane fixture", creator="ace_start", priority="high",
        admission={
            "source_type": "evidence", "source_ref": "fixture:lane-integration-2",
            "why_now": "prove the second lane is refused",
            "evidence": [{"source": "test", "content": "fixture"}],
            "expected_result": "a refusal naming the holder",
            "verification_method": "assert refusal",
            "risk": "low", "estimated_scope": "small",
        },
        outputs={"execution_discipline": {}},
    )
    second = ace_start(pool2, task2.task_id, "window-b", 300,
                       regions=["core/lane_a.py"], base_dir=str(root))
    assert second["status"] == "REJECTED"
    assert second["reason"] == "lane_claim_refused"
    assert second["lane_detail"]["held_by"] == "window-a"


def test_a_hotspot_region_refuses_a_foreign_lane_at_start(workspace):
    root, pool = workspace
    from core.window_lane import LaneRegistry

    owners = {"regions": {"core/miner_pool": "nim-lane"}, "shared": []}
    registry = LaneRegistry(root, owners_table=owners, state_path=root / "claims.json")
    task = _first_task(pool)
    refused = ace_start(pool, task.task_id, "governance-lane", 300,
                        regions=["core/miner_pool/miner_pool.py"],
                        lane_registry=registry)
    assert refused["status"] == "REJECTED"
    assert refused["lane_detail"]["owner"] == "nim-lane"


def test_the_hotspot_owner_may_start_on_its_own_region(workspace):
    root, pool = workspace
    from core.window_lane import LaneRegistry

    owners = {"regions": {"core/miner_pool": "nim-lane"}, "shared": []}
    registry = LaneRegistry(root, owners_table=owners, state_path=root / "claims.json")
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "nim-lane", 300,
                       regions=["core/miner_pool/miner_pool.py"],
                       lane_registry=registry)
    assert result["status"] == "STARTED"


def test_partial_lane_claims_are_not_left_behind(workspace):
    root, pool = workspace
    from core.window_lane import LaneRegistry

    owners = {"regions": {"core/governance": "governance-lane"}, "shared": []}
    registry = LaneRegistry(root, owners_table=owners, state_path=root / "claims.json")
    task = _first_task(pool)
    refused = ace_start(pool, task.task_id, "nim-lane", 300,
                        regions=["core/ok_region.py", "core/governance/x.py"],
                        lane_registry=registry)
    assert refused["status"] == "REJECTED"
    assert registry.list_claims() == [], "half a lane claim is an unowned file believed held"


# --- an undeclared region is recorded, never refused -------------------------
#
# `--region` stays optional: refusing here would break every in-flight window,
# and the 1098 uncommitted items in the main checkout were all produced by
# starts that declared nothing. What was missing is not enforcement but the
# fact: "a window started work holding no file region" is exactly what the lane
# convention exists to make visible. These tests pin that the fact is recorded,
# that it costs no claim, and that omitting base_dir still behaves as before.


def test_an_undeclared_start_is_recorded_not_refused(workspace):
    root, pool = workspace
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "window-a", 300, base_dir=str(root))
    assert result["status"] == "STARTED"
    assert result["lane_declaration"] == "UNCLAIMED_RECORDED"
    assert result["lane_claims"] == []


def test_an_undeclared_start_writes_an_audit_row_naming_the_task(workspace):
    import json

    root, pool = workspace
    task = _first_task(pool)
    ace_start(pool, task.task_id, "window-a", 300, base_dir=str(root))

    state = root / "08_GOVERNANCE" / "lanes" / "lane_claims.json"
    assert state.is_file(), "the audit has to be readable or the fact is not durable"
    rows = json.loads(state.read_text(encoding="utf-8"))["audit"]
    assert len(rows) == 1
    assert rows[0]["event"] == "unclaimed_start"
    assert rows[0]["lane"] == "window-a"
    assert rows[0]["task_id"] == task.task_id


def test_recording_an_undeclared_start_does_not_claim_the_files(workspace):
    root, pool = workspace
    from core.window_lane import LaneRegistry

    task = _first_task(pool)
    ace_start(pool, task.task_id, "window-a", 300, base_dir=str(root))

    registry = LaneRegistry(root, state_path=root / "claims.json")
    assert registry.list_claims() == [], (
        "recording an absence must not manufacture a claim - an unowned file "
        "believed held is worse than a file known to be unowned"
    )


def test_a_declared_start_reports_claimed(workspace):
    root, pool = workspace
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "window-a", 300,
                       regions=["core/lane_a.py"], base_dir=str(root))
    assert result["status"] == "STARTED"
    assert result["lane_declaration"] == "CLAIMED"


def test_a_start_without_base_dir_stays_none(workspace):
    """The legacy call shape has no registry to record into; it must not break."""
    root, pool = workspace
    task = _first_task(pool)
    result = ace_start(pool, task.task_id, "window-a", 300)
    assert result["status"] == "STARTED"
    assert result["lane_declaration"] == "NONE"