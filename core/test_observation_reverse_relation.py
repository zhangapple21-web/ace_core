"""A declared field that is always empty is worse than a short-lived true one.

`Observation.related_tasks` was declared in the dataclass and initialised to `[]` in
`record()`, and nothing in the repository ever appended to it. So the observation store
carried a field that claimed a reverse edge to work and could not represent any - while
the durable copy of that relation lives on the task side, where the phase-2 audit
counted 970 persistent `source_obs_id` pointers.

Two things are worth being precise about:

  the edge is still short-lived   it lives on the observation, and the observation store
                                 is a rolling window of roughly 200 rows. Filling the
                                 field does not make history durable; the task-side
                                 evidence copy does that.
  perception is not work         `mark_consumed` is also called with
                                 `PERCEPTION_ONLY`, which is a disposition rather than
                                 a task. Recording it as a relation would invent work
                                 that does not exist.

Idempotence matters more than it looks: the converter can call `mark_consumed` for the
same observation more than once across processes, and this file is rewritten whole each
time.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.observation import RuntimeObserver  # noqa: E402


def _observer(tmp_path) -> RuntimeObserver:
    return RuntimeObserver(data_dir=str(tmp_path / "observations"))


def _record(observer: RuntimeObserver, **overrides):
    payload = {"description": "fragment backlog", "system_state": {"pending_scan": 7847},
               "source": "daemon_loop", "category": "gap"}
    payload.update(overrides)
    return observer.record(**payload)


def _row(observer: RuntimeObserver, obs_id: str):
    return next(row for row in observer._observations if row.obs_id == obs_id)


def test_a_consumed_observation_records_the_reverse_relation(tmp_path):
    observer = _observer(tmp_path)
    obs = _record(observer)
    assert obs.related_tasks == [], "precondition: the field starts empty"

    observer.mark_consumed(obs.obs_id, "RQ-20261018-001")

    assert _row(observer, obs.obs_id).related_tasks == ["RQ-20261018-001"], (
        "the reverse relation was not recorded"
    )
    reloaded = RuntimeObserver(data_dir=str(observer.observations_file.parent))
    assert _row(reloaded, obs.obs_id).related_tasks == ["RQ-20261018-001"], (
        "the reverse relation did not survive the write"
    )


def test_recording_the_same_relation_repeatedly_does_not_duplicate_it(tmp_path):
    observer = _observer(tmp_path)
    obs = _record(observer)

    for _ in range(5):
        observer.mark_consumed(obs.obs_id, "RQ-20261018-001")

    assert _row(observer, obs.obs_id).related_tasks == ["RQ-20261018-001"], (
        f"the relation duplicated: {_row(observer, obs.obs_id).related_tasks}"
    )


def test_a_second_task_for_the_same_observation_is_recorded_too(tmp_path):
    """The field is a list of relations, not a mirror of task_generated."""
    observer = _observer(tmp_path)
    obs = _record(observer)

    observer.mark_consumed(obs.obs_id, "RQ-1")
    observer.mark_consumed(obs.obs_id, "RQ-2")

    assert _row(observer, obs.obs_id).related_tasks == ["RQ-1", "RQ-2"]


def test_perception_only_is_not_recorded_as_a_task_relation(tmp_path):
    observer = _observer(tmp_path)
    obs = _record(observer, source="host_session", category="environment_change",
                  system_state={})

    observer.mark_consumed(obs.obs_id, "PERCEPTION_ONLY")

    row = _row(observer, obs.obs_id)
    assert row.task_generated == "PERCEPTION_ONLY", "the disposition itself must be kept"
    assert row.related_tasks == [], (
        f"a perception disposition was recorded as work: {row.related_tasks}"
    )


def test_an_observation_written_before_this_field_existed_still_loads(tmp_path):
    """Old rows carry `related_tasks: null`; the store must not break on them."""
    observer = _observer(tmp_path)
    obs = _record(observer)
    path = observer.observations_file
    lines = path.read_text(encoding="utf-8").splitlines()
    import json

    patched = []
    for line in lines:
        row = json.loads(line)
        if row["obs_id"] == obs.obs_id:
            row.pop("related_tasks", None)
        patched.append(json.dumps(row, ensure_ascii=False))
    path.write_text("\n".join(patched) + "\n", encoding="utf-8")

    fresh = RuntimeObserver(data_dir=str(path.parent))
    reloaded_obs = next(row for row in fresh._observations if row.obs_id == obs.obs_id)
    assert reloaded_obs.related_tasks == [], (
        f"a row without the field came back as {reloaded_obs.related_tasks!r}"
    )
    fresh.mark_consumed(obs.obs_id, "RQ-20261018-002")
    assert _row(fresh, obs.obs_id).related_tasks == ["RQ-20261018-002"], (
        "consuming a legacy row did not record the relation"
    )