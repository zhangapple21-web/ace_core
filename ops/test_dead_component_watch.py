"""Dead-component watch: escalate regressions, never the standing count.

Two things make this worth testing rather than eyeballing. First, the scan had a
real bug: `from x import Y` is an ast.alias, not an ast.Name, so walking only
Name and Attribute reported nearly every importable component as dead - 977
phantoms out of 1014. Second, the alerting rule is the whole point: the standing
count is a structural fact, not an incident, and reporting it every cycle would
train the reader to ignore the channel.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ops.dead_component_watch as watch  # noqa: E402


class _Recorder:
    """Stands in for RuntimeObserver and records what it was told."""

    def __init__(self):
        self.calls = []

    def record(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def _make_workspace(tmp_path, *, live, dead, test_uses_dead=False):
    """A workspace with three kinds of file, mirroring the real layout."""
    core = tmp_path / "core"
    core.mkdir(parents=True, exist_ok=True)
    ops = tmp_path / "ops"
    ops.mkdir(parents=True, exist_ok=True)

    # a live component: defined in core, imported by a consumer
    for name in live:
        (core / f"{name.lower()}.py").write_text(
            f"class {name}:\n    pass\n", encoding="utf-8")
    (core / "consumer.py").write_text(
        "\n".join(f"from .{name.lower()} import {name}" for name in live) + "\n",
        encoding="utf-8")

    # a dead component: defined in core, referenced nowhere
    for name in dead:
        (core / f"{name.lower()}.py").write_text(
            f"class {name}:\n    pass\n", encoding="utf-8")

    # a test file that calls a live component (real evidence of wiring)
    (ops / "test_something.py").write_text(
        "\n".join(f"def test_{name.lower()}():\n    assert {name} is not None"
                  for name in live) + "\n", encoding="utf-8")
    if test_uses_dead:
        with (ops / "test_something.py").open("a", encoding="utf-8") as handle:
            handle.write("\n\ndef test_orphan():\n    assert DeadThing is not None\n")
    return tmp_path


# ------------------------------------------------------------------ the scan

def test_an_imported_component_is_not_dead(tmp_path):
    """The ast.alias bug: import is the most common way a component is referenced."""
    _make_workspace(tmp_path, live=["LiveThing"], dead=[])
    dead = watch.scan(tmp_path)
    assert "LiveThing" not in dead, "an imported component is wired, not dead"


def test_a_component_nothing_references_is_dead(tmp_path):
    _make_workspace(tmp_path, live=[], dead=["DeadThing"])
    dead = watch.scan(tmp_path)
    assert "DeadThing" in dead
    assert dead["DeadThing"]["file"] == "core/deadthing.py"


def test_a_test_file_contributes_no_definitions(tmp_path):
    """pytest instantiates test classes by discovery, so they are never referenced."""
    _make_workspace(tmp_path, live=["LiveThing"], dead=[])
    (tmp_path / "ops" / "test_widget.py").write_text(
        "class WidgetTests:\n    def test_ok(self):\n        assert True\n", encoding="utf-8")
    dead = watch.scan(tmp_path)
    assert "WidgetTests" not in dead, "a test class is not a dead production component"


def test_a_test_that_calls_a_component_is_evidence_of_wiring(tmp_path):
    _make_workspace(tmp_path, live=["LiveThing"], dead=[])
    assert watch._has_tests(tmp_path, "LiveThing") is True


def test_has_tests_matches_whole_names_only(tmp_path):
    """An unanchored substring match reported 927 of 1014 as carrying tests."""
    (tmp_path / "ops").mkdir(parents=True, exist_ok=True)
    # a compound name containing it, and no bare occurrence anywhere
    (tmp_path / "ops" / "test_note.py").write_text(
        "# mentions ConstitutionHierarchy and nothing else whatsoever\n",
        encoding="utf-8")
    assert watch._has_tests(tmp_path, "Constitution") is False
    (tmp_path / "ops" / "test_note.py").write_text(
        "def test_it():\n    assert Constitution is not None\n", encoding="utf-8")
    assert watch._has_tests(tmp_path, "Constitution") is True


# ------------------------------------------------------------------ alerting

def test_the_standing_count_is_never_escalated(tmp_path):
    """A fact about the library is not an incident.

    Re-reporting the standing count every cycle is the wolf-crying failure that
    makes a guardian get ignored, which is the same as having none.
    """
    _make_workspace(tmp_path, live=[], dead=["DeadThing"])
    # a test names it, so it is an orphaned-intent candidate the first time
    (tmp_path / "ops" / "test_deadthing.py").write_text(
        "def test_deadthing():\n    assert DeadThing is not None\n", encoding="utf-8")
    observer = _Recorder()
    first = watch.run(tmp_path, observer, force=True)
    assert first["status"] == "SCANNED"
    assert first["escalated"], "the first snapshot may establish intent"
    # second run against the same snapshot: nothing new, so nothing escalated
    observer2 = _Recorder()
    second = watch.run(tmp_path, observer2, force=True)
    assert second["escalated"] == [], "an unchanged snapshot must not re-escalate"
    assert observer2.calls == []


def test_a_newly_dead_component_is_a_regression(tmp_path):
    _make_workspace(tmp_path, live=["LiveThing"], dead=[])
    watch.run(tmp_path, _Recorder(), force=True)

    # remove every reference: the import and the test that named it
    (tmp_path / "core" / "consumer.py").write_text("", encoding="utf-8")
    (tmp_path / "ops" / "test_something.py").write_text(
        "def test_nothing():\n    assert True\n", encoding="utf-8")
    observer = _Recorder()
    report = watch.run(tmp_path, observer, force=True)
    regressed = [e for e in report["escalated"] if e["kind"] == "regressed"]
    assert regressed, "a component that lost its call site is a break"
    assert regressed[0]["name"] == "LiveThing"
    assert observer.calls, "and it is reported through the observation channel"
    assert observer.calls[0]["category"] == "structural_gap"


def test_escalation_is_capped(tmp_path):
    """One bad snapshot must not flood the channel."""
    names = [f"Dead{i}" for i in range(10)]
    _make_workspace(tmp_path, live=[], dead=names)
    for name in names:
        (tmp_path / "ops" / f"test_{name.lower()}.py").write_text(
            f"def test_{name.lower()}():\n    assert {name} is not None\n", encoding="utf-8")
    report = watch.run(tmp_path, _Recorder(), force=True)
    assert len(report["escalated"]) <= watch.MAX_ESCALATIONS_PER_RUN


def test_an_interval_is_respected(tmp_path):
    from datetime import datetime, timezone

    _make_workspace(tmp_path, live=[], dead=["DeadThing"])
    watch.run(tmp_path, _Recorder(), force=True)
    snapshot = json.loads((tmp_path / watch.SNAPSHOT).read_text(encoding="utf-8"))
    snapshot["at"] = datetime.now(timezone.utc).isoformat()
    (tmp_path / watch.SNAPSHOT).write_text(
        json.dumps(snapshot), encoding="utf-8")
    observer = _Recorder()
    report = watch.run(tmp_path, observer)
    assert report["status"] == "NOT_DUE"
    assert "interval" in report["reason"]
    assert observer.calls == []


def test_the_snapshot_records_what_it_saw(tmp_path):
    _make_workspace(tmp_path, live=["LiveThing"], dead=["DeadThing"])
    report = watch.run(tmp_path, _Recorder(), force=True)
    snapshot_path = tmp_path / watch.SNAPSHOT
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["contract_version"] == watch.CONTRACT_VERSION
    assert "DeadThing" in snapshot["dead"]
    assert "LiveThing" not in snapshot["dead"]
    assert report["dead_definitions"] == len(snapshot["dead"])