"""find_related(from_lane=...): a window may ask about its own learning.

The shared substrate is one pile. Before this, a window asking about its own
subject got everybody else's answers mixed in - which is how a shared result
decays back into noise, and how "the same words appeared somewhere" gets read as
"this window learned".

One distinction pinned here, because it is the whole point and easy to lose:
a reading of another window's deposit is NOT reuse. A lesson rises to a shared
result only when the window that deposited it reads it back. So scoping prefers
own-lane results and keeps the rest visible - a preference, never a wall,
because lineage may weight a retrieval but must not seal off what another window
learned.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.experience_deposition import ExperienceDeposition  # noqa: E402
from core.task import Task  # noqa: E402


def _deposit(root, task_id, conclusion, lane):
    deposition = ExperienceDeposition(str(root))
    task = Task(task_id=task_id, title="t", hypothesis=conclusion)
    return deposition.deposit(task=task, experience_type="lesson",
                              conclusion=conclusion, lane=lane)


def test_scoping_prefers_the_readers_own_deposits(tmp_path):
    _deposit(tmp_path, "RQ-A", "validator bypass shared about gate design", "adjudication")
    _deposit(tmp_path, "RQ-B", "validator bypass shared about gate design", "tombstoning")
    deposition = ExperienceDeposition(str(tmp_path))

    first = deposition.find_related("validator bypass", from_lane="adjudication",
                                    actor="adjudication")[0]
    assert first.depositing_lane == "adjudication", (
        "a window's own deposit should come first when it asks"
    )


def test_scoping_keeps_other_lanes_visible(tmp_path):
    """A preference, not a wall: lineage weights retrieval, never seals it."""
    _deposit(tmp_path, "RQ-A", "validator bypass shared about gate design", "adjudication")
    _deposit(tmp_path, "RQ-B", "validator bypass shared about gate design", "tombstoning")
    deposition = ExperienceDeposition(str(tmp_path))

    found = deposition.find_related("validator bypass", from_lane="adjudication",
                                    actor="adjudication")
    lanes = {e.depositing_lane for e in found}
    assert lanes == {"adjudication", "tombstoning"}, (
        "scoping must not hide what another window deposited"
    )


def test_an_unscoped_search_is_unchanged(tmp_path):
    """The default stays open; nobody has to opt in to see the whole store."""
    _deposit(tmp_path, "RQ-A", "validator bypass shared about gate design", "adjudication")
    _deposit(tmp_path, "RQ-B", "validator bypass shared about gate design", "tombstoning")
    deposition = ExperienceDeposition(str(tmp_path))
    found = deposition.find_related("validator bypass", actor="researcher")
    assert {e.depositing_lane for e in found} == {"adjudication", "tombstoning"}


def test_a_reader_still_leaves_its_attribution(tmp_path):
    """Reading somebody else's deposit records who read, not who wrote."""
    _deposit(tmp_path, "RQ-A", "validator bypass shared about gate design", "adjudication")
    deposition = ExperienceDeposition(str(tmp_path))
    deposition.find_related("validator bypass", from_lane="tombstoning",
                           actor="tombstoning")
    loaded = deposition.get_all(limit=10)[0]
    assert loaded.last_used_by == "tombstoning", (
        "the reader is named on the record it read"
    )