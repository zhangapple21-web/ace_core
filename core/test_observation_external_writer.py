"""Two processes write this store, and only one of them reloads it.

Found in production rather than by reading the code, which is why it is worth
pinning precisely.

The daemon holds one `RuntimeObserver` for hours. The structural watches are
separate processes that append to the same file through a different instance.
`_append()` writes in append mode, so a watch's record does reach disk - and then
`mark_consumed()` rewrites the whole file from the long-lived process's memory,
which is a snapshot taken at startup. The record is gone, no error is raised, and
the escalation that produced it looks complete.

The loss was observed directly. At 14:16:33 a SYSTEM-run watch recorded
`DAEMON_STOPPED` with `task_generated=None`; the file was 206 rows and contained
it. At 14:17:49 the daemon (started 14:16:1x) called `mark_consumed()` and the file
became 203 rows with no trace of it - and no task was ever created from it. The
same rewrite is why the store has never contained a single record from
`incident_reachability_watch` or `daemon_liveness_watch`, the two independent
watches whose whole purpose is to escalate into it.

That matters beyond tidiness. An escalation channel that silently drops the
findings of the processes meant to use it is the difference between a safety net
and a safety net that reports having been installed.

The fix is one-directional and the tests say so: the on-disk file is the shared
append log and supplies the order, so rows another writer appended are adopted,
while this process's own rows that the disk lacks are not re-appended - they are
older than the window the file keeps, and re-appending them would move ancient
records to the newest position.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.observation import RuntimeObserver  # noqa: E402


def _data_dir(root: Path) -> str:
    return str(root / "06_RUNTIME" / "ace" / "data" / "observations")


def _rows(data_dir: str):
    path = Path(data_dir) / "observations.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _index(data_dir: str):
    path = Path(data_dir) / "observation_index.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("signatures", {})


def test_a_long_lived_writer_cannot_erase_a_watch_finding(tmp_path):
    """The record reached the file; that must be enough to keep it."""
    data_dir = _data_dir(tmp_path)
    daemon = RuntimeObserver(data_dir=data_dir)
    own = daemon.record(description="daemon observed something",
                        system_state={"n": 1}, source="daemon_loop", category="gap")
    assert len(_rows(data_dir)) == 1

    # A separate process - the watch - appends to the same store.
    watch = RuntimeObserver(data_dir=data_dir)
    finding = watch.record(
        description="daemon liveness watch: heartbeat status=stale pid=21796",
        system_state={"kind": "DAEMON_STOPPED"},
        severity="high",
        source="daemon_liveness_watch",
        category="structural_gap",
        dedup_key="daemon_liveness:DAEMON_STOPPED",
    )
    assert len(_rows(data_dir)) == 2

    # The daemon consumes its own record and rewrites the file from memory.
    daemon.mark_consumed(own.obs_id, "RQ-20260101-001")

    ids = [row["obs_id"] for row in _rows(data_dir)]
    assert finding.obs_id in ids, (
        "the watch's finding was erased by a writer that never read it; the "
        "escalation reached the file and was destroyed before anything could "
        "convert it, which is how a safety net reports itself as installed"
    )


def test_a_finding_written_before_the_consuming_rewrite_is_still_findable(tmp_path):
    """Adoption has to happen before the lookup, or the id is simply unknown."""
    data_dir = _data_dir(tmp_path)
    daemon = RuntimeObserver(data_dir=data_dir)
    daemon.record(description="daemon", system_state={}, source="daemon_loop",
                  category="gap")

    watch = RuntimeObserver(data_dir=data_dir)
    finding = watch.record(description="watch finding", system_state={},
                           severity="high", source="daemon_liveness_watch",
                           category="structural_gap", dedup_key="k:1")

    # The converter may hold an id read from disk by another code path; adopting
    # the external rows first is what makes it resolvable here at all.
    daemon.mark_consumed(finding.obs_id, "RQ-20260101-002")
    stored = [row for row in _rows(data_dir) if row["obs_id"] == finding.obs_id]
    assert stored and stored[0]["task_generated"] == "RQ-20260101-002"


def test_an_external_dedup_key_survives_the_index_rewrite(tmp_path):
    """The observations file is not the only thing rewritten from memory."""
    data_dir = _data_dir(tmp_path)
    daemon = RuntimeObserver(data_dir=data_dir)
    daemon.record(description="daemon", system_state={}, source="daemon_loop",
                  category="gap")

    watch = RuntimeObserver(data_dir=data_dir)
    watch.record(description="watch finding", system_state={}, severity="high",
                 source="daemon_liveness_watch", category="structural_gap",
                 dedup_key="daemon_liveness:DAEMON_STOPPED")
    signature = RuntimeObserver._dedup_signature(
        "daemon_liveness:DAEMON_STOPPED", "daemon_liveness_watch", "structural_gap")
    assert signature in _index(data_dir), "the watch's key never reached the index"

    # Any later record from the long-lived process rewrites the index from memory.
    daemon.record(description="daemon again", system_state={"n": 2},
                  source="daemon_loop", category="gap")

    assert signature in _index(data_dir), (
        "the index rewrite dropped the other process's key; losing it makes the "
        "watch's next report look like a different incident and produces a "
        "duplicate task per tick"
    )


def test_the_same_finding_is_not_appended_twice_while_unconsumed(tmp_path):
    """What makes an hourly re-assertion cheap instead of noisy."""
    data_dir = _data_dir(tmp_path)
    observer = RuntimeObserver(data_dir=data_dir)
    first = observer.record(description="watch finding", system_state={"n": 1},
                            severity="high", source="daemon_liveness_watch",
                            category="structural_gap", dedup_key="daemon_liveness:X")
    second = observer.record(description="watch finding", system_state={"n": 2},
                             severity="high", source="daemon_liveness_watch",
                             category="structural_gap", dedup_key="daemon_liveness:X")
    assert first.obs_id == second.obs_id
    assert len(_rows(data_dir)) == 1


def test_two_writers_cannot_mint_the_same_observation_id(tmp_path):
    """One counter file, two processes that loaded it at different moments.

    Both hold the same value; the later writer writes first. Nothing about that is
    exotic - it is what happens whenever a watch runs while the daemon is alive -
    and the consequence is not cosmetic: adoption resolves records by id, so two
    rows sharing one id makes `mark_consumed` able to mark the wrong record.
    """
    data_dir = _data_dir(tmp_path)
    daemon = RuntimeObserver(data_dir=data_dir)
    watch = RuntimeObserver(data_dir=data_dir)

    minted_by_watch = watch.record(
        description="watch finding", system_state={}, severity="high",
        source="daemon_liveness_watch", category="structural_gap",
        dedup_key="daemon_liveness:Z")
    minted_by_daemon = daemon.record(
        description="daemon observation", system_state={}, source="daemon_loop",
        category="gap")

    assert minted_by_watch.obs_id != minted_by_daemon.obs_id
    ids = [row["obs_id"] for row in _rows(data_dir)]
    assert len(ids) == len(set(ids))


def test_a_consumed_finding_can_be_re_asserted(tmp_path):
    """The other half: once it has been read, a still-true finding returns."""
    data_dir = _data_dir(tmp_path)
    observer = RuntimeObserver(data_dir=data_dir)
    first = observer.record(description="watch finding", system_state={},
                            severity="high", source="daemon_liveness_watch",
                            category="structural_gap", dedup_key="daemon_liveness:Y")
    observer.mark_consumed(first.obs_id, "RQ-20260101-003")
    second = observer.record(description="watch finding", system_state={},
                             severity="high", source="daemon_liveness_watch",
                             category="structural_gap", dedup_key="daemon_liveness:Y")
    assert second.obs_id != first.obs_id, (
        "a consumed observation is not evidence about the world, so the next "
        "report has to be a new record"
    )
    assert len(_rows(data_dir)) == 2
