"""Evidence inflation in the research path: the rework loop guarantees non-convergence.

Reproduces the live failure on RQ-20261004-044, which carried 25 stored evidence
items that collapsed to 2 unique (source, content) pairs, then reached
MAX_UNCHANGED_REVIEWS=4 and was blocked as `blocked_non_convergent`.

Two compounding causes, both in core/task_roles.py::Researcher.research_task:

1. Within one call, memory enrichment iterates `keywords[:5]` and appends
   `hits[:2]` per keyword. When several keywords match the same memory record, the
   identical {source, content} is appended several times.

2. Across calls, the loop does `task.add_evidence(...)`, which appends without
   comparing against what the task already carries. research_task is re-invoked on
   each rework cycle, so identical evidence is re-appended every cycle.

Together they make the stored count grow 5, 10, 15, 20, 25 while the unique set
stays at 2. The validator signature is computed over the deduplicated set, so it
never changes, so `stable_validation` is always true, so `unchanged_review_count`
climbs to the limit and the task is declared non-convergent.

**Researching the task harder makes convergence strictly less likely.** That is the
defect: a fail-closed guard whose own input path defeats it.

The same file already carries a comment recording an earlier episode of this bug
class ("Promoting them inflated evidence counts and repeatedly injected the same
generic runtime text into rework tasks"). That fix filtered by evidence *type*. The
duplicate dimension was left unfixed.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.task import Task, TaskPool  # noqa: E402
from core.task_roles import Researcher  # noqa: E402


class _OverlapIndex:
    """A memory index where every keyword returns the same top record.

    This is the normal case for a task whose title and hypothesis share terms, and
    it is what makes the within-call fan-out emit duplicates.
    """

    def __init__(self, records):
        self._records = records
        self.calls = 0

    def search(self, keyword=None, limit=10):
        self.calls += 1
        return list(self._records)[:limit]


def _pool(tmp):
    return TaskPool(os.path.join(str(tmp), "pool"))


def _make_task(tmp_path, task_id="RQ-TEST-001"):
    pool = _pool(tmp_path)
    task = Task(
        task_id=task_id,
        title="calibrate intra_agreement threshold",
        hypothesis="the 0.5 cut is uncalibrated",
    )
    pool.update_task(task)
    return pool, task


def _researcher(pool, records):
    return Researcher(task_pool=pool, memory_index=_OverlapIndex(records))


RECORDS = [
    {"id": "a1", "content": "archivist digest of RQ-1", "source": "archivist:a1", "title": "r1"},
    {"id": "b2", "content": "archivist digest of RQ-2", "source": "archivist:b2", "title": "r2"},
]


def test_single_call_does_not_emit_the_same_memory_hit_twice(tmp_path):
    """Within one research call, overlapping keywords must not duplicate a record."""
    pool, task = _make_task(tmp_path)
    r = _researcher(pool, RECORDS)

    r.research_task(task)

    pairs = [(e.get("source", ""), e.get("content", "")) for e in task.evidence]
    assert len(pairs) == len(set(pairs)), (
        "duplicate (source, content) emitted inside a single research call: %r" % (pairs,)
    )


def test_repeated_research_does_not_inflate_stored_evidence(tmp_path):
    """Re-researching must not grow the count when nothing new was found.

    This is the loop that blocked RQ-20261004-044: five rework cycles turned 2 unique
    records into 25 stored items.
    """
    pool, task = _make_task(tmp_path)
    r = _researcher(pool, RECORDS)

    for _ in range(5):
        r.research_task(task)

    pairs = [(e.get("source", ""), e.get("content", "")) for e in task.evidence]
    assert len(pairs) == len(set(pairs)), (
        "re-researching the same task appended duplicate evidence %d times "
        "(unique=%d)" % (len(pairs), len(set(pairs)))
    )
    assert len(pairs) == 2, "expected the 2 real records, got %d" % len(pairs)


def test_genuinely_new_evidence_is_still_added(tmp_path):
    """The fix must not become a blanket refusal to record evidence."""
    pool, task = _make_task(tmp_path)

    _researcher(pool, RECORDS).research_task(task)
    before = len(task.evidence)
    assert before == 2, before

    new = [{"id": "c3", "content": "a genuinely new measurement", "source": "lab:c3", "title": "c"}]
    _researcher(pool, new).research_task(task)

    assert len(task.evidence) == before + 1, (
        "new evidence was dropped: %d -> %d" % (before, len(task.evidence))
    )


def test_stored_count_matches_the_count_the_validator_actually_sees(tmp_path):
    """The defect in one assertion: len(task.evidence) must equal the unique set.

    On RQ-20261004-044 this read 25 while the validator saw 2. A reader checking
    `len(task.evidence)` was told there were 25 pieces of evidence.
    """
    from core.task_roles import Validator

    pool, task = _make_task(tmp_path)
    r = _researcher(pool, RECORDS)
    for _ in range(5):
        r.research_task(task)

    stored = len(task.evidence or [])
    seen_by_validator = len(Validator._unique_evidence(task))
    assert stored == seen_by_validator, (
        "stored evidence count lies: stored=%d validator_sees=%d" % (stored, seen_by_validator)
    )


if __name__ == "__main__":
    import tempfile

    failures = 0
    for fn in (
        test_single_call_does_not_emit_the_same_memory_hit_twice,
        test_repeated_research_does_not_inflate_stored_evidence,
        test_genuinely_new_evidence_is_still_added,
        test_stored_count_matches_the_count_the_validator_actually_sees,
    ):
        with tempfile.TemporaryDirectory() as td:
            try:
                fn(td)
                print("PASS %s" % fn.__name__)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s\n      %s" % (fn.__name__, exc))
    print("failures=%d" % failures)
    raise SystemExit(1 if failures else 0)