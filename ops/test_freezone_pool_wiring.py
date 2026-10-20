"""The relay must write into a pool that something actually serves.

Defect record
-------------
On 2026-10-13, `ace_daemon` handed `FreeZoneReflectionRelay` the isolated
`task_pool_freezone` TaskPool. That pool has no lifecycle at all: its only
subdirectory is `pending`, and no Researcher, Validator, Guardian, or Archivist
is constructed against it. The relay therefore wrote 67 admitted verification
tasks into a pool nothing reads, while the main pool - which already held 16
tasks by this same creator, most archived after a full lifecycle - sat with
`pending=0`.

`pending=0` is the tell. A runtime whose admission path works but whose queue
is empty is not a runtime with no work; it is a runtime whose work is going
somewhere invisible. These tests pin the wiring and the observable symptom, so
the failure cannot come back quietly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.free_zone_reflection_relay import FreeZoneReflectionRelay  # noqa: E402
from core.task import TaskPool  # noqa: E402


def test_the_relays_task_pool_is_one_the_lifecycle_serves(tmp_path):
    """Point the relay at a pool with a lifecycle, not an isolated one.

    The invariant is behavioural, not a name: the pool must be one whose statuses
    the lifecycle can actually reach. A pool carrying only `pending` is a black
    hole - work enters and never changes state, which is what happened to the
    67 orphans.
    """
    from core.task import TASK_STATUSES

    for status in ("pending", "active", "review", "approved", "archived"):
        assert status in TASK_STATUSES
    # A TaskPool handed to the lifecycle is created against the full layout.
    served = TaskPool(str(tmp_path / "served"))
    assert (tmp_path / "served" / "active").is_dir()
    assert (tmp_path / "served" / "archived").is_dir()

    black_hole = tmp_path / "black_hole"
    (black_hole / "pending").mkdir(parents=True)
    assert not (black_hole / "active").exists(), (
        "a pool with only pending is one nothing drives"
    )


def test_an_unserved_pool_can_be_told_apart_from_the_filesystem(tmp_path):
    """The freezone pool's shape was the fingerprint of the defect.

    An audit that cannot read the daemon can still find a black hole: a task_pool
    directory whose only subdirectory is `pending` is a pool no lifecycle was
    built against.
    """
    live = TaskPool(str(tmp_path / "live"))
    assert all((tmp_path / "live" / s).is_dir() for s in ("pending", "active", "archived"))

    dead = tmp_path / "dead"
    (dead / "pending").mkdir(parents=True)
    live_statuses = {p.name for p in (tmp_path / "live").iterdir() if p.is_dir()}
    dead_statuses = {p.name for p in dead.iterdir() if p.is_dir()}
    assert dead_statuses < live_statuses
    assert "active" not in dead_statuses


def test_the_daemon_wires_the_relay_to_the_pool_it_serves():
    """Read the daemon source: the relay's task_pool must be self.task_pool.

    This is a source-level pin because the defect was a wiring choice, and a
    unit test constructed against a stub daemon would have passed happily on the
    broken wiring - the relay does not care which pool it is given.
    """
    import ace_daemon

    source = open(ace_daemon.__file__, encoding="utf-8").read()
    assert "task_pool=self.task_pool," in source, (
        "the reflection relay must write into the pool with a lifecycle"
    )
    assert "task_pool=self.freezone_task_pool" not in source, (
        "freezone_task_pool has no lifecycle; the relay must not write there"
    )


def test_a_relay_task_reaches_a_live_state_in_the_served_pool(tmp_path):
    """End to end: the relay's output is claimable by the lifecycle."""
    pool = TaskPool(str(tmp_path / "served"))
    relay = FreeZoneReflectionRelay(
        tmp_path,
        sandbox_root=tmp_path / "07_SANDBOX" / "free_research",
        task_pool=pool,
    )
    source = tmp_path / "07_SANDBOX" / "free_research" / "distillations"
    source.mkdir(parents=True, exist_ok=True)
    incoming = tmp_path / "08_GOVERNANCE" / "free_zone_exchange" / "receipts"
    incoming.mkdir(parents=True, exist_ok=True)

    import json

    from core.free_zone_reality_bridge import FreeZoneRealityBridge
    from core.free_zone_reality_bridge import _digest as bridge_digest

    dist = {
        "contract_version": "ace.free_research_sandbox.v1",
        "mode": "DISTILLATION_ONLY",
        "production_integration": False,
        "automatic_delivery": False,
        "automatic_promotion": False,
        "automatic_task_creation": False,
        "experiment_id": "EXP-TEST-RELAY",
        "distillation_hash": "",
        "source_record_hash": "",
        "status": "OPEN_QUESTION",
        "pattern": "a free-zone result may carry an ACE-verifiable lead",
        "outcome": "INCONCLUSIVE",
        "pollution_flags": [],
    }
    experiments = source.parent / "experiments"
    experiments.mkdir(parents=True, exist_ok=True)
    experiment = {
        "contract_version": "ace.free_research_sandbox.v1",
        "production_integration": False,
        "experiment_id": "EXP-TEST-RELAY",
        "hypothesis": "a free-zone result may carry an ACE-verifiable lead",
        "outcome": "INCONCLUSIVE",
        "metadata": {"source_kind": "free_zone_test"},
        "record_hash": "",
        "pollution_flags": [],
    }
    record_input = dict(experiment)
    record_input.pop("record_hash", None)
    experiment["record_hash"] = bridge_digest(record_input)
    (experiments / "EXP-TEST-RELAY.json").write_text(
        json.dumps(experiment, ensure_ascii=False), encoding="utf-8")

    # the distillation binds to the experiment by its record hash, then is itself
    # digested over the payload with distillation_hash removed
    dist["source_record_hash"] = experiment["record_hash"]
    hash_input = dict(dist)
    hash_input.pop("distillation_hash", None)
    dist["distillation_hash"] = bridge_digest(hash_input)
    (source / "EXP-TEST-RELAY.json").write_text(
        json.dumps(dist, ensure_ascii=False), encoding="utf-8")
    receipt_path = incoming / "EX-TEST.json"
    receipt_path.write_text(json.dumps({
        "origin": {"exchange_id": "EX-TEST", "receipt_sha256": "b" * 64},
    }, ensure_ascii=False), encoding="utf-8")

    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=source.parent)
    receipt = bridge.build(source / "EXP-TEST-RELAY.json", relay._mapping(
        source / "EXP-TEST-RELAY.json", dist, receipt_path))

    task = relay._create_followup_task(
        source / "EXP-TEST-RELAY.json", dist, receipt_path, receipt)
    assert task is not None, "the relay must create the follow-up task"
    assert task.task_id

    # the task must be claimable - which only the main-pool lifecycle does
    claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
    assert claimed is not None, "relay work must be claimable, not stranded"
    assert pool.load_task(task.task_id).status == "active"

    # and it must be idempotent: a second call returns the same task
    again = relay._create_followup_task(
        source / "EXP-TEST-RELAY.json", dist, receipt_path, receipt)
    assert again is not None and again.task_id == task.task_id
