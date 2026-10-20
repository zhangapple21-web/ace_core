"""window_write: the write IS the asking.

The failure this pins is a registry that ends up decorative because each window
was asked to check permission at each of a hundred write sites and eventually
forgot. `may_write` is correct; the problem was who had to call it. Here the
write goes through the chokepoint, so a window cannot write a file it does not
hold without being refused - and the refusal names who does hold it.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.window_lane import LaneRegistry  # noqa: E402
from core.window_write import WindowRefused, window_write  # noqa: E402


@pytest.fixture()
def workspace(tmp_path):
    owners = {"regions": {"core/governance": "governance-lane",
                          "07_SANDBOX": "sandbox-lane"}, "shared": ["shared"]}
    registry = LaneRegistry(tmp_path, owners_table=owners, state_path=tmp_path / "claims.json")
    return tmp_path, registry


class _Recorder:
    def __init__(self):
        self.calls = []

    def record(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


# ------------------------------------------------------------------ the refusals

def test_a_write_outside_the_lane_is_refused(workspace):
    tmp_path, registry = workspace
    registry.claim("sandbox-lane", "07_SANDBOX/free_research")
    with pytest.raises(WindowRefused) as caught:
        window_write(tmp_path, "07_SANDBOX/free_research/x.json", {"a": 1},
                     lane="governance-lane", registry=registry)
    # the refusal names the lane that does hold it, whichever guard fired
    detail = caught.value.detail
    assert detail.get("held_by") == "sandbox-lane" or detail.get("owner") == "sandbox-lane"
    assert not (tmp_path / "07_SANDBOX" / "free_research" / "x.json").exists()


def test_a_refusal_names_the_owner_not_just_no(workspace):
    tmp_path, registry = workspace
    with pytest.raises(WindowRefused) as caught:
        window_write(tmp_path, "core/governance/x.json", {}, lane="sandbox-lane",
                     registry=registry)
    assert caught.value.detail["owner"] == "governance-lane"


def test_a_refusal_is_observed_not_silent(workspace):
    tmp_path, registry = workspace
    observer = _Recorder()
    with pytest.raises(WindowRefused):
        window_write(tmp_path, "core/governance/x.json", {}, lane="sandbox-lane",
                     registry=registry, observer=observer)
    assert observer.calls
    assert observer.calls[0]["category"] == "structural_gap"


def test_a_refusal_records_nothing_when_the_observer_is_broken(workspace):
    """A missing observer must not turn a refusal into a write."""
    tmp_path, registry = workspace
    class _Broken:
        def record(self, **kwargs):
            raise RuntimeError("observer down")
    with pytest.raises(WindowRefused):
        window_write(tmp_path, "core/governance/x.json", {}, lane="sandbox-lane",
                     registry=registry, observer=_Broken())


# ------------------------------------------------------------------ the writes

def test_a_lane_writes_its_own_region(workspace):
    tmp_path, registry = workspace
    registry.claim("sandbox-lane", "07_SANDBOX/free_research")
    result = window_write(tmp_path, "07_SANDBOX/free_research/x.json", {"a": 1},
                          lane="sandbox-lane", registry=registry)
    assert result["status"] == "WRITTEN"
    on_disk = json.loads((tmp_path / "07_SANDBOX" / "free_research" / "x.json")
                         .read_text(encoding="utf-8"))
    assert on_disk == {"a": 1}


def test_a_hotspot_owner_writes_without_a_claim(workspace):
    """Ownership is the claim for a hotspot: the owner never needs to lease it."""
    tmp_path, registry = workspace
    result = window_write(tmp_path, "core/governance/x.json", {}, lane="governance-lane",
                          registry=registry)
    assert result["owner"] == "governance-lane"
    assert (tmp_path / "core" / "governance" / "x.json").exists()


def test_shared_regions_need_no_claim(workspace):
    tmp_path, registry = workspace
    result = window_write(tmp_path, "shared/a.txt", "hello", lane="anyone-lane",
                          registry=registry)
    assert result["status"] == "WRITTEN"
    assert (tmp_path / "shared" / "a.txt").read_text(encoding="utf-8") == "hello"


def test_an_unclaimed_region_is_refused_by_default(workspace):
    """``allow_unclaimed`` is the escape hatch, and it is off by default."""
    tmp_path, registry = workspace
    with pytest.raises(WindowRefused):
        window_write(tmp_path, "somewhere/a.txt", "x", lane="anyone", registry=registry)
    allowed = window_write(tmp_path, "somewhere/a.txt", "x", lane="anyone",
                           registry=registry, allow_unclaimed=True)
    assert allowed["status"] == "WRITTEN"


def test_content_shapes_are_preserved(workspace):
    tmp_path, registry = workspace
    registry.claim("sandbox-lane", "07_SANDBOX/free_research")
    window_write(tmp_path, "07_SANDBOX/free_research/plain.md", "text",
                 lane="sandbox-lane", registry=registry)
    window_write(tmp_path, "07_SANDBOX/free_research/rec.json", {"k": "v"},
                 lane="sandbox-lane", registry=registry)
    assert (tmp_path / "07_SANDBOX" / "free_research" / "plain.md").read_text(
        encoding="utf-8") == "text"
    assert json.loads((tmp_path / "07_SANDBOX" / "free_research" / "rec.json").read_text(
        encoding="utf-8")) == {"k": "v"}
