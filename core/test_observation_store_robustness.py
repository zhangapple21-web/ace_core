"""One malformed row must not be able to empty the observation store.

What the store does today
-------------------------
`_load()` builds the whole list inside one try, and any failure - a truncated line, a
row written before a field existed, an encoding hiccup - falls into
`self._observations = []`. The store then believes it has never seen an observation.
The rewrite that follows writes from that empty list, so a single bad row is enough to
replace two hundred good ones with nothing, silently, in a process that will never say
a word about it.

Two things make that survivable, and both are small:

  one row is one row   a row that cannot be built is skipped and counted, so the other
                       rows still load and the loss is visible rather than total
  the rewrite is atomic  the store is written to a temporary file and moved into place,
                       so a process killed mid-write leaves the previous file intact
                       rather than a truncated one that poisons the next load

The atomic pattern is not invented here: `core/continuity_audit.py::_atomic_write` and
`ops/runtime_identity_receipt.py::write_receipt` already do exactly this.

Why this is filed as its own concern
------------------------------------
The store is shared by several processes, at least one of them runs unattended, and the
day's earlier defect - a rewrite from a stale in-memory snapshot erasing another
process's rows - was fixed by making appends adopt. That fix made appends safer; it did
nothing about a row that cannot be parsed, which is the failure that turns a partial
problem into a total one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.observation import RuntimeObserver  # noqa: E402


def _observer(tmp_path) -> RuntimeObserver:
    return RuntimeObserver(data_dir=str(tmp_path / "observations"))


def _record(observer: RuntimeObserver, description: str = "condition"):
    return observer.record(description=description, system_state={"n": 1},
                           source="daemon_loop", category="gap")


def test_one_unparseable_row_does_not_empty_the_store(tmp_path):
    observer = _observer(tmp_path)
    keep = _record(observer, "a row that must survive")
    other = _record(observer, "another row that must survive")
    path = observer.observations_file

    # A row written by an older writer, or truncated by a crash mid-write.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"obs_id": "OBS-BROKEN", "description": "no fields"})
                     + "\n")

    fresh = RuntimeObserver(data_dir=str(path.parent))
    loaded = {row.obs_id for row in fresh._observations}

    assert keep.obs_id in loaded, (
        "a malformed row emptied the store; the other rows were lost with it"
    )
    assert other.obs_id in loaded, "a malformed row cost unrelated observations"
    assert len(fresh.skipped_rows) == 1, (
        f"the skipped row was not counted, so the loss is invisible: "
        f"{fresh.skipped_rows!r}"
    )
    assert fresh.skipped_rows[0].startswith("OBS-BROKEN"), (
        f"the skip does not name the row that was lost: {fresh.skipped_rows!r}"
    )
    assert "missing" in fresh.skipped_rows[0], (
        f"the skip does not say what was wrong with it: {fresh.skipped_rows!r}"
    )


def test_a_write_interrupted_mid_rewrite_leaves_the_previous_file_intact(tmp_path):
    """The reason to move the rename in: a crash must not truncate the store."""
    observer = _observer(tmp_path)
    first = _record(observer, "survives the interrupted rewrite")
    path = observer.observations_file
    before = path.read_text(encoding="utf-8")

    class _Exploding(dict):
        """A row whose serialisation fails halfway through the rewrite."""

        def items(self):
            raise RuntimeError("serialisation died mid-write")

    original = json.dumps
    calls = {"n": 0}

    def flaky(obj, *args, **kwargs):
        if isinstance(obj, dict) and "obs_id" in obj:
            calls["n"] += 1
            if calls["n"] > 1:
                raise RuntimeError("serialisation died mid-write")
        return original(obj, *args, **kwargs)

    json.dumps = flaky
    try:
        try:
            fresh = RuntimeObserver(data_dir=str(path.parent))
            fresh.mark_consumed(first.obs_id, "RQ-20261018-001")
        except RuntimeError:
            pass  # the crash is the point; the store must not be the casualty
    finally:
        json.dumps = original

    after = path.read_text(encoding="utf-8")
    assert first.obs_id in after, (
        "an interrupted rewrite destroyed the store instead of leaving it alone"
    )
    readable = RuntimeObserver(data_dir=str(path.parent))
    assert first.obs_id in {row.obs_id for row in readable._observations}, (
        "the store no longer loads after an interrupted rewrite"
    )
    assert not list(path.parent.glob("*.tmp")), (
        "an interrupted rewrite left temporary files beside the store"
    )


def test_the_store_still_works_after_a_row_is_skipped(tmp_path):
    """Skipping must not make the store refuse to be written again - and the next
    rewrite heals the malformed row away.

    The loss is reported at load time, when it happens and can still be investigated.
    Once the store is rewritten the bad row is simply gone, which is the better
    outcome: a file that cannot be read no longer sits in the middle of the history.
    """
    observer = _observer(tmp_path)
    keep = _record(observer, "row before the damage")
    path = observer.observations_file
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json at all\n")

    fresh = RuntimeObserver(data_dir=str(path.parent))
    assert len(fresh.skipped_rows) == 1, (
        f"the malformed row was not reported at load time: {fresh.skipped_rows!r}"
    )
    assert keep.obs_id in {row.obs_id for row in fresh._observations}

    obs = _record(fresh, "row after the damage")
    fresh.mark_consumed(obs.obs_id, "RQ-20261018-002")

    reloaded = RuntimeObserver(data_dir=str(path.parent))
    stored = {row.obs_id: row for row in reloaded._observations}
    assert obs.obs_id in stored, "the store stopped accepting new rows"
    assert stored[obs.obs_id].task_generated == "RQ-20261018-002"
    assert reloaded.skipped_rows == [], (
        "the malformed row survived a rewrite that should have healed it"
    )
    assert keep.obs_id in stored, "healing one row lost an unrelated one"