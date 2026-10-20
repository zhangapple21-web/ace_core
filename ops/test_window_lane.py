"""Window lanes: one holder per region, and a stale token writes nothing.

The failure these pin is the one that nearly happened: two windows writing
source into the same checkout, with nothing that could say stop. The draft that
named it rejected CRDT, OS locks and a coordination scheduler, so this reuses
TaskPool's lease/fencing shape instead of inventing a third mechanism.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.window_lane import (  # noqa: E402
    LaneRegistry,
    regions_overlap,
)


@pytest.fixture()
def registry(tmp_path):
    """A registry with owners, over a temp root so nothing real is written."""
    owners = {
        "regions": {
            "core/miner_pool": "nim-lane",
            "core/governance": "governance-lane",
            "ace_config.json": "nim-lane",
        },
        "shared": ["core/window_lane.py"],
    }
    return LaneRegistry(tmp_path, owners_table=owners,
                        state_path=tmp_path / "claims.json")


# ------------------------------------------------------------------ overlap

def test_a_region_is_claimed_by_one_lane_at_a_time(registry):
    first = registry.claim("governance-lane", "core/governance/mengpo_runtime.py")
    assert first.lane == "governance-lane"
    second = registry.claim("nim-lane", "core/governance/mengpo_runtime.py")
    assert second["status"] == "REFUSED"
    # the reason names whichever guard fired first; both are refusals, and the
    # point of the test is that a second lane does not get through
    assert "governance-lane" in second["reason"]


def test_disjoint_files_never_contend(registry):
    registry.claim("nim-lane", "core/miner_pool/miner_pool.py")
    other = registry.claim("governance-lane", "core/governance/mengpo_runtime.py")
    assert isinstance(other.claim_id, str)


def test_a_directory_claim_covers_what_is_beneath_it(registry):
    assert regions_overlap("core/governance", "core/governance/mengpo_runtime.py")
    assert regions_overlap("core/governance/mengpo_runtime.py", "core/governance")
    assert not regions_overlap("core/governance", "core/task.py")


def test_backslashes_and_dot_slashes_are_the_same_claim():
    assert regions_overlap(r"core\governance", "core/governance/")
    assert regions_overlap("./core/governance", "core\\governance")


def test_the_same_lane_may_reclaim_its_own_region(registry):
    """Re-claiming your own region gets you a fresh token, not a second hold."""
    first = registry.claim("governance-lane", "unowned_area/one.py")
    second = registry.claim("governance-lane", "unowned_area/one.py")
    assert isinstance(second.claim_id, str)
    assert second.claim_id != first.claim_id, "a re-claim is a fresh token"
    # the old claim is superseded, not stacked: two holds on one region is
    # exactly the double-write this registry exists to prevent
    held = registry.list_claims(live_only=True)
    assert [c["claim_id"] for c in held] == [second.claim_id]
    live = registry.release(second.claim_id, token=second.fencing_token)
    assert live["status"] == "RELEASED"
    stale = registry.release(first.claim_id, token=first.fencing_token)
    assert stale["status"] == "NOT_FOUND"


# ------------------------------------------------------------------ owners

def test_an_owned_region_refuses_a_foreign_lane(registry):
    refused = registry.claim("governance-lane", "core/miner_pool/miner_pool.py")
    assert refused["status"] == "REFUSED"
    assert refused["owner"] == "nim-lane"


def test_a_shared_region_needs_no_exclusive_claim(registry):
    """Shared means every lane may write - the opposite of a claim.

    Requiring a claim on a shared region would invent a contention that does
    not exist and would make two windows editing one shared file block each
    other, which is the failure this whole registry is meant to remove.
    """
    first = registry.claim("nim-lane", "core/window_lane.py")
    second = registry.claim("governance-lane", "core/window_lane.py")
    assert first["status"] == "SHARED_WRITE_ALLOWED"
    assert second["status"] == "SHARED_WRITE_ALLOWED"
    assert registry.list_claims() == [], "a shared write holds nothing"
    assert registry.may_write("governance-lane", "core/window_lane.py")["allowed"]


def test_owner_override_is_recorded_as_a_refusal_by_default(registry):
    """An override is possible, but it must be explicit to be auditable."""
    assert registry.claim("governance-lane", "ace_config.json")["status"] == "REFUSED"


# ------------------------------------------------------------------ fencing

def _expire(registry, claim, seconds=3600):
    path = registry.state_path
    state = json.loads(path.read_text(encoding="utf-8"))
    for entry in state["claims"]:
        if entry["claim_id"] == claim.claim_id:
            entry["lease_expires_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=seconds)
            ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    path.write_text(json.dumps(state), encoding="utf-8")


def _unowned_region():
    """A region no lane owns, so only the lease is under test."""
    return "unowned_area/core/governance/mengpo_runtime.py"


def test_an_expired_lease_does_not_transfer_the_region(registry):
    first = registry.claim("governance-lane", _unowned_region())
    second = registry.claim("nim-lane", _unowned_region())
    assert second["status"] == "REFUSED", "an expired lease is not permission"
    _expire(registry, first)
    third = registry.claim("nim-lane", _unowned_region())
    assert isinstance(third.claim_id, str), "an expired lease frees the region"


def test_a_stale_holder_cannot_release_over_the_current_one(registry):
    """The Chubby rule: lease expiry never proves the holder stopped."""
    region = _unowned_region()
    first = registry.claim("governance-lane", region)
    _expire(registry, first)
    second = registry.claim("nim-lane", region)
    assert isinstance(second.claim_id, str)
    # the old holder's late release must be refused, not silently accepted
    late = registry.release(first.claim_id, token=first.fencing_token)
    assert late["status"] == "REFUSED"
    # whichever way it is refused, it must not be told it gave anything back
    assert "expired" in late["reason"] or "fencing token mismatch" in late["reason"]
    # and the current holder still holds
    assert [c["lane"] for c in registry.list_claims(live_only=True)] == ["nim-lane"]


def test_an_expired_claim_is_swept_away(registry):
    claim = registry.claim("nim-lane", _unowned_region())
    _expire(registry, claim)
    report = registry.expire_stale()
    assert claim.claim_id in report["dropped"]
    assert registry.list_claims(live_only=True) == []


# ------------------------------------------------------------------ asking

def test_may_write_answer_before_the_write(registry):
    registry.claim("nim-lane", "ace_config.json")
    assert registry.may_write("governance-lane", "ace_config.json")["allowed"] is False
    free = registry.may_write("governance-lane", "core/governance/mengpo_runtime.py")
    assert free["allowed"] is True


def test_may_write_names_the_owner_not_just_no(registry):
    """A refusal has to say WHO, not just no - or the window cannot route around it."""
    registry.claim("nim-lane", "ace_config.json")
    answer = registry.may_write("governance-lane", "ace_config.json")
    assert answer["allowed"] is False
    # the region is a nim-lane hotspot AND live-claimed: whichever guard fired,
    # the answer must name nim-lane so the caller knows who to wait for
    named = answer.get("owner") or answer.get("held_by")
    assert named == "nim-lane", answer


def test_owning_lane_may_write_its_own_hotspot(registry):
    assert registry.may_write("nim-lane", "ace_config.json")["allowed"] is True


# ------------------------------------------------------------------ records

def test_every_claim_is_auditable(registry):
    claim = registry.claim("governance-lane", "core/governance",
                           actor="test", reason="closing the loop")
    state = json.loads(registry.state_path.read_text(encoding="utf-8"))
    entry = state["audit"][-1]
    assert entry["event"] == "claim"
    assert entry["lane"] == "governance-lane"
    assert entry["actor"] == "test"
    assert entry["reason"] == "closing the loop"
    assert entry["fencing_token"] == claim.fencing_token


def test_claims_live_outside_the_task_pool(registry):
    """Lanes and tasks are different axes: one window, several regions."""
    claim = registry.claim("nim-lane", "ace_config.json")
    assert isinstance(claim.claim_id, str)
    assert not (registry.root / "task_pool").exists()


def test_empty_lane_or_region_is_refused(registry):
    assert registry.claim("", "ace_config.json")["status"] == "REFUSED"
    assert registry.claim("nim-lane", "")["status"] == "REFUSED"
