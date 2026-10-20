"""A rewrite of a task's content must be visible on the task itself.

RQ-20261006-009 recorded this as "归档记录静默改写：update_task经_transition落盘
只touch不留audit痕迹". Measured on 2026-10-18, the shape of the report was right
and the status half was already covered: every status change goes through
move_task, which writes a `transition` row. What was missing was the other half -
a hypothesis, result, evidence list or tag set written by update_task landed with
no trace at all. The ledger's drift check only fires on counters, so a rewritten
record was indistinguishable from one nobody touched.

The task record is evidence for every conclusion drawn from it, so these tests
pin both halves: a real rewrite is recorded, and the ordinary bookkeeping writes
that dominate production stay silent.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.task import TaskPool

ADMISSION = {
    "source_type": "system_observation",
    "source_ref": "OBS-probe",
    "why_now": "audit visibility probe",
    "evidence": [{"observation_id": "OBS-probe", "content": "c", "source": "s"}],
    "expected_result": "r",
    "verification_method": "m",
    "risk": "low",
    "estimated_scope": "one",
}


def _pool(tmp_path) -> TaskPool:
    return TaskPool(str(tmp_path / "pool"))


def _task(pool: TaskPool, title: str = "probe"):
    return pool.create_task(
        title=title, hypothesis="h", creator="test", priority="low", admission=ADMISSION
    )


def _rewrite_rows(task):
    return [row for row in (task.audit_log or []) if row.get("event") == "content_rewritten"]


class ContentRewriteIsAudited(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rewritten_hypothesis_is_recorded_with_the_field_name(self):
        pool = _pool(self.tmp_path)
        task = _task(pool)

        task.hypothesis = "SILENTLY REWRITTEN"
        self.assertTrue(pool.update_task(task))

        stored = pool.load_task(task.task_id)
        rows = _rewrite_rows(stored)
        self.assertEqual(len(rows), 1, "the rewrite must leave exactly one audit row")
        self.assertEqual(rows[0]["fields"], ["hypothesis"])
        self.assertIn("at", rows[0])

    def test_appending_a_note_is_not_a_rewrite(self):
        """A note being added is the system recording what it just did.

        Measured on 2026-10-18, this guard fired on every write in a live task:
        RQ-20261018-281 reached 20 rows in under an hour, half its audit log,
        every row naming the same append-only fields. That is not evidence of
        tampering - each entry carries its own timestamp and is already the
        record - it is evidence the guard was watching the wrong thing and would
        have buried a real rewrite in noise.
        """
        pool = _pool(self.tmp_path)
        task = _task(pool)

        task.add_research_note("first observation")
        self.assertTrue(pool.update_task(task))
        first = len(_rewrite_rows(pool.load_task(task.task_id)))

        task = pool.load_task(task.task_id)
        task.add_research_note("second observation")
        pool.update_task(task)
        self.assertEqual(
            len(_rewrite_rows(pool.load_task(task.task_id))),
            first,
            "appending must not be recorded as a rewrite",
        )

    def test_rewriting_an_existing_note_is_still_a_rewrite(self):
        """The guard must not become a way to edit the record quietly."""
        pool = _pool(self.tmp_path)
        task = _task(pool)
        task.add_research_note("original")
        pool.update_task(task)
        baseline = len(_rewrite_rows(pool.load_task(task.task_id)))

        task = pool.load_task(task.task_id)
        task.research_notes = [{"content": "original", "at": "2026-10-18T00:00:00"}]
        pool.update_task(task)

        rows = _rewrite_rows(pool.load_task(task.task_id))
        self.assertEqual(len(rows), baseline + 1)
        self.assertIn("research_notes", rows[-1]["fields"])

    def test_appending_while_altering_an_existing_entry_is_a_rewrite(self):
        """The subtle case: grow the list but quietly change what was in it."""
        pool = _pool(self.tmp_path)
        task = _task(pool)
        task.add_research_note("original")
        pool.update_task(task)
        baseline = len(_rewrite_rows(pool.load_task(task.task_id)))

        task = pool.load_task(task.task_id)
        existing = dict(task.research_notes[0])
        existing["content"] = "altered"
        task.research_notes = [existing, {"content": "new", "at": "2026-10-18T00:00:01"}]
        pool.update_task(task)

        rows = _rewrite_rows(pool.load_task(task.task_id))
        self.assertEqual(len(rows), baseline + 1, "a rewrite hidden inside an append")
        self.assertIn("research_notes", rows[-1]["fields"])

    def test_outputs_growing_is_not_a_rewrite_but_changing_is(self):
        pool = _pool(self.tmp_path)
        task = _task(pool)
        outputs = dict(task.outputs or {})
        outputs["first_key"] = {"v": 1}
        task.outputs = outputs
        pool.update_task(task)
        baseline = len(_rewrite_rows(pool.load_task(task.task_id)))

        task = pool.load_task(task.task_id)
        grown = dict(task.outputs or {})
        grown["second_key"] = {"v": 2}
        task.outputs = grown
        pool.update_task(task)
        self.assertEqual(len(_rewrite_rows(pool.load_task(task.task_id))), baseline)

        task = pool.load_task(task.task_id)
        changed = dict(task.outputs or {})
        changed["first_key"] = {"v": 99}
        task.outputs = changed
        pool.update_task(task)
        self.assertIn("outputs", _rewrite_rows(pool.load_task(task.task_id))[-1]["fields"])

    def test_each_content_field_is_covered(self):
        pool = _pool(self.tmp_path)
        task = _task(pool)

        task.result = {"summary": "a result that was not there before"}
        task.priority = "high"
        pool.update_task(task)

        fields = set(_rewrite_rows(pool.load_task(task.task_id))[0]["fields"])
        self.assertIn("result", fields)
        self.assertIn("priority", fields)

    def test_status_change_is_audited_as_a_transition(self):
        """The half that already worked, pinned so it cannot silently regress."""
        pool = _pool(self.tmp_path)
        task = _task(pool)

        moved = pool.move_task(task.task_id, "active", actor="researcher", reason="lease", task=task)
        self.assertIsNotNone(moved)

        events = [row.get("event") for row in (moved.audit_log or [])]
        self.assertIn("transition", events)

    def test_a_no_op_update_stays_silent(self):
        """Bookkeeping writes dominate production; they must not become noise."""
        pool = _pool(self.tmp_path)
        task = _task(pool)
        pool.update_task(task)  # no change at all
        baseline = len(_rewrite_rows(pool.load_task(task.task_id)))

        for _ in range(5):
            current = pool.load_task(task.task_id)
            pool.update_task(current)

        self.assertEqual(
            len(_rewrite_rows(pool.load_task(task.task_id))),
            baseline,
            "an unchanged record must not log a rewrite",
        )

    def test_the_stored_record_still_holds_the_new_value(self):
        """Auditing must not become a veto."""
        pool = _pool(self.tmp_path)
        task = _task(pool)

        task.hypothesis = "the corrected hypothesis"
        self.assertTrue(pool.update_task(task))
        self.assertEqual(pool.load_task(task.task_id).hypothesis, "the corrected hypothesis")


if __name__ == "__main__":
    unittest.main()