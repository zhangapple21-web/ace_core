"""The whole loop, end to end, on real files.

Everything else in this suite pins a piece. This one runs the chain the owner
described - a window thinks, deposits a verified result into the shared
substrate under its own name, and a later window reads it back with the reader
attributed - and asserts nothing is lost at any seam. It writes into 09_KNOWLEDGE
on the real tree and cleans up after itself, because a loop proved only in a
fixture is a loop proved nowhere.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.experience_deposition import ExperienceDeposition  # noqa: E402
from core.task import Task  # noqa: E402

ROOT = Path(r"C:\tmp/ace_core")
KNOWLEDGE = ROOT / "09_KNOWLEDGE"


def _cleanup(ids):
    for path in KNOWLEDGE.rglob("*.json"):
        for exp_id in ids:
            if exp_id in path.name:
                try:
                    path.with_suffix(".json.mengpo-backup").unlink()
                except OSError:
                    pass
                try:
                    path.unlink()
                except OSError:
                    pass


def test_the_shared_loop_closes_on_the_real_tree():
    created: list[str] = []
    backup_index = None
    index_path = KNOWLEDGE / "experiences.json"
    try:
        if index_path.exists():
            backup_index = index_path.read_bytes()
        deposition = ExperienceDeposition(str(KNOWLEDGE))

        # 1. a window thinks and deposits
        task = Task(task_id="RQ-LOOPTEST-1", title="loop",
                    hypothesis="a window learned that the gate must refuse late writes")
        first = deposition.deposit(
            task=task, experience_type="lesson",
            conclusion="a window learned that the gate must refuse late writes "
                       "when the lease has already expired",
            lane="tombstoning")
        created.append(first.experience_id)
        assert first.depositing_lane == "tombstoning"

        # 2. the record is on disk under that name
        on_disk = json.loads(
            (KNOWLEDGE / "lesson" / f"{first.experience_id}.json").read_text(encoding="utf-8"))
        assert on_disk["depositing_lane"] == "tombstoning"

        # 3. a different window asks, and gets it, first
        later = deposition.find_related(
            "gate must refuse late writes", from_lane="tombstoning",
            actor="adjudication")
        assert later, "the second window found nothing in the shared substrate"
        assert later[0].depositing_lane == "tombstoning"
        # 4. the reader is named on the record, not the writer
        assert later[0].last_used_by == "adjudication"

        # 5. and the loop remembers it was used, so reuse is provable
        assert later[0].reference_count >= 1
    finally:
        _cleanup(created)
        if backup_index is not None:
            index_path.write_bytes(backup_index)
        elif index_path.exists():
            index_path.unlink()