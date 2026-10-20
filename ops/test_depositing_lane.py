"""depositing_lane: the shared substrate says who put what in it.

The three windows deposit into 09_KNOWLEDGE by three different code paths, and
before this the result was an anonymous pile: a steward reading a lesson could
not tell whether tombstoning, adjudication, or the archive path had learned it.
That matters because the whole point of the shared substrate is that a window can
use what another window verified, and "who taught this" is the difference between
inheritance and noise.

Two things pinned here, because both are easy to get wrong:

1. Old records still load. 09_KNOWLEDGE holds records written before this
   field existed; a required field would brick the store, so the default is
   "unattributed" and says so rather than inventing a window.
2. The lane does not gate the write. 09_KNOWLEDGE is the surface every window
   is meant to reach; a refusal here would close the very door the field opens.
   Provenance, not permission.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.experience_deposition import Experience  # noqa: E402
from core.task import Task  # noqa: E402


def _lesson(**overrides):
    base = {
        "experience_id": "LESSON-test-1",
        "source_task_id": "RQ-TEST-1",
        "experience_type": "lesson",
        "conclusion": "a lesson worth keeping",
        "evidence": [],
        "constraints_updated": [],
        "related_concepts": [],
    }
    base.update(overrides)
    return Experience(**base)


def test_a_new_deposit_records_its_lane(tmp_path):
    from core.experience_deposition import ExperienceDeposition

    deposition = ExperienceDeposition(str(tmp_path))
    task = Task(task_id="RQ-LANE-1", title="t", hypothesis="h")
    result = deposition.deposit(
        task=task, experience_type="lesson",
        conclusion="learned something", lane="tombstoning")
    assert result.depositing_lane == "tombstoning"
    on_disk = json.loads(
        (tmp_path / "lesson" / f"{result.experience_id}.json").read_text(encoding="utf-8"))
    assert on_disk["depositing_lane"] == "tombstoning"


def test_a_deposit_without_a_lane_says_unattributed(tmp_path):
    from core.experience_deposition import ExperienceDeposition

    deposition = ExperienceDeposition(str(tmp_path))
    task = Task(task_id="RQ-LANE-2", title="t", hypothesis="h")
    result = deposition.deposit(task=task, experience_type="lesson")
    assert result.depositing_lane == "unattributed"


def test_an_old_record_without_the_field_still_loads(tmp_path):
    """The store holds records written before this field existed."""
    legacy = {
        "experience_id": "LESSON-legacy-1",
        "source_task_id": "RQ-OLD-1",
        "experience_type": "lesson",
        "conclusion": "an old lesson",
        "evidence": [],
        "constraints_updated": [],
        "related_concepts": [],
        "tags": ["lesson"],
        "data_class": "PRIVATE",
        "created_at": "2026-09-01T00:00:00",
        "reference_count": 0,
        "last_used_at": "2026-09-01T00:00:00",
        "last_used_by": "unspecified",
    }
    loaded = Experience.from_dict(legacy)
    assert loaded.experience_id == "LESSON-legacy-1"
    assert loaded.depositing_lane == "unattributed", (
        "an absent lane must be reported as absent, not invented"
    )


def test_a_real_legacy_record_on_disk_still_loads():
    """Not a fixture: an actual 09_KNOWLEDGE record from before the field."""
    import glob

    candidates = sorted(glob.glob(
        r"C:\tmp/ace_core/09_KNOWLEDGE/*/*.json"), key=os.path.getmtime)
    assert candidates, "no knowledge records found to check"
    loaded = 0
    for path in candidates[:50]:
        data = json.loads(open(path, encoding="utf-8").read())
        if not isinstance(data, dict) or "experience_id" not in data:
            continue
        record = Experience.from_dict(data)
        assert record.depositing_lane in {"unattributed"} or record.depositing_lane
        loaded += 1
    assert loaded, "no loadable records were checked"


def test_a_redeposited_record_gains_its_lane(tmp_path):
    """The bug that made last week's work look done when it was not.

    deposit() early-returns when a record already exists, and the first
    implementation returned the stored record untouched - so a lane passed on
    any later attempt was silently dropped. All 67 tombstoning lessons came back
    unattributed because every one of them hit that branch.
    """
    from core.experience_deposition import ExperienceDeposition

    deposition = ExperienceDeposition(str(tmp_path))
    task = Task(task_id="RQ-REDEP-1", title="t", hypothesis="h")
    first = deposition.deposit(task=task, experience_type="lesson")
    assert first.depositing_lane == "unattributed"

    second = deposition.deposit(task=task, experience_type="lesson",
                                conclusion="a sharper reading of the same task",
                                lane="adjudication")
    assert second.experience_id == first.experience_id, "still the same record"
    assert second.depositing_lane == "adjudication", (
        "a later depositor must be visible, not silently dropped"
    )
    on_disk = json.loads(
        (tmp_path / "lesson" / f"{first.experience_id}.json").read_text(encoding="utf-8"))
    assert on_disk["depositing_lane"] == "adjudication", (
        "and the store must agree, not just the returned object"
    )


def test_relabelling_never_changes_the_stored_conclusion(tmp_path):
    """Attributing a lane must not quietly rewrite what the record says."""
    from core.experience_deposition import ExperienceDeposition

    deposition = ExperienceDeposition(str(tmp_path))
    task = Task(task_id="RQ-REDEP-2", title="t", hypothesis="h")
    first = deposition.deposit(task=task, experience_type="lesson",
                               conclusion="the conclusion as first written")
    before = (tmp_path / "lesson" / f"{first.experience_id}.json").read_text(encoding="utf-8")

    deposition.deposit(task=task, experience_type="lesson",
                       conclusion="a different conclusion someone now prefers",
                       lane="other-lane")
    after = (tmp_path / "lesson" / f"{first.experience_id}.json").read_text(encoding="utf-8")

    before_data, after_data = json.loads(before), json.loads(after)
    assert before_data["conclusion"] == after_data["conclusion"], (
        "a lane rewrite must leave the record's meaning alone"
    )
    assert after_data["depositing_lane"] == "other-lane"


def test_a_lane_never_overwrites_one_already_recorded(tmp_path):
    """First writer wins: re-attribution fills a gap, it does not revise history."""
    from core.experience_deposition import ExperienceDeposition

    deposition = ExperienceDeposition(str(tmp_path))
    task = Task(task_id="RQ-REDEP-3", title="t", hypothesis="h")
    deposition.deposit(task=task, experience_type="lesson", lane="first-lane")
    again = deposition.deposit(task=task, experience_type="lesson", lane="second-lane")
    assert again.depositing_lane == "first-lane", (
        "provenance records who put it there first; a later writer cannot "
        "take credit for a record already attributed"
    )


def test_the_lane_is_provenance_not_permission():
    """The field must not become a gate: this substrate is shared by design."""
    import inspect

    from core.experience_deposition import ExperienceDeposition

    source = inspect.getsource(ExperienceDeposition.deposit)
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("raise") and "lane" in stripped:
            raise AssertionError(f"a lane must not be able to refuse a deposit: {stripped}")
    assert "depositing_lane" in source