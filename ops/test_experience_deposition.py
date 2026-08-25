import json
from datetime import datetime as RealDateTime
from types import SimpleNamespace

import core.experience_deposition as deposition_module
from core.experience_deposition import ExperienceDeposition


class FrozenDateTime:
    @classmethod
    def now(cls):
        return RealDateTime(2026, 8, 25, 9, 4, 41)


def task(task_id, hypothesis="durable conclusion", decision="experience"):
    return SimpleNamespace(
        task_id=task_id,
        guardian_decision=decision,
        hypothesis=hypothesis,
        title=f"Task {task_id}",
        evidence=[{"source": "runtime:test", "content": "measured evidence"}],
        tags=["test"],
    )


def test_two_tasks_deposited_in_the_same_second_never_overwrite(monkeypatch, tmp_path):
    monkeypatch.setattr(deposition_module, "datetime", FrozenDateTime)
    deposition = ExperienceDeposition(str(tmp_path))

    first = deposition.deposit_from_task(task("RQ-001"))
    second = deposition.deposit_from_task(task("RQ-002"))

    assert first.experience_id != second.experience_id
    files = sorted((tmp_path / "pattern").glob("EXP-*.json"))
    assert len(files) == 2
    assert {
        json.loads(path.read_text(encoding="utf-8"))["source_task_id"]
        for path in files
    } == {"RQ-001", "RQ-002"}


def test_replaying_the_same_task_and_type_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(deposition_module, "datetime", FrozenDateTime)
    deposition = ExperienceDeposition(str(tmp_path))

    first = deposition.deposit(task("RQ-replay", hypothesis="original"), "pattern")
    replay = deposition.deposit(task("RQ-replay", hypothesis="changed replay"), "pattern")

    assert replay.experience_id == first.experience_id
    files = list((tmp_path / "pattern").glob("EXP-*.json"))
    assert len(files) == 1
    persisted = json.loads(files[0].read_text(encoding="utf-8"))
    assert persisted["conclusion"] == "original"
    assert persisted["source_task_id"] == "RQ-replay"


def test_same_task_may_have_one_record_per_distinct_experience_type(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    source = task("RQ-multi")

    pattern = deposition.deposit(source, "pattern")
    lesson = deposition.deposit(source, "lesson")

    assert pattern.experience_id != lesson.experience_id
    assert len(list((tmp_path / "pattern").glob("EXP-*.json"))) == 1
    assert len(list((tmp_path / "lesson").glob("EXP-*.json"))) == 1


def test_legacy_record_is_reused_instead_of_duplicated(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    legacy_id = "EXP-20260825090441"
    legacy_path = tmp_path / "pattern" / f"{legacy_id}.json"
    legacy = {
        "experience_id": legacy_id,
        "source_task_id": "RQ-legacy",
        "experience_type": "pattern",
        "conclusion": "legacy conclusion",
        "evidence": [],
        "constraints_updated": [],
        "related_concepts": [],
        "tags": ["legacy"],
        "created_at": "2026-08-25T09:04:41",
        "reference_count": 0,
        "last_used_at": "2026-08-25T09:04:41",
    }
    legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
    deposition._save_index({
        legacy_id: {
            "path": str(legacy_path),
            "type": "pattern",
            "conclusion": "legacy conclusion",
            "source_task": "RQ-legacy",
        }
    })

    replay = deposition.deposit(task("RQ-legacy", hypothesis="new"), "pattern")

    assert replay.experience_id == legacy_id
    assert replay.conclusion == "legacy conclusion"
    assert len(list((tmp_path / "pattern").glob("EXP-*.json"))) == 1


def test_deterministic_id_is_safe_for_unusual_task_identifiers(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    experience = deposition.deposit(task("RQ:unsafe/path"), "observation")

    path = tmp_path / "observation" / f"{experience.experience_id}.json"
    assert path.exists()
    assert ":" not in experience.experience_id
    assert "/" not in experience.experience_id


def test_persisted_experience_round_trips_through_get_all(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    created = deposition.deposit(task("RQ-roundtrip"), "pattern")

    loaded = deposition.get_all("pattern")

    assert [item.experience_id for item in loaded] == [created.experience_id]
    assert loaded[0].source_task_id == "RQ-roundtrip"


def test_archived_experience_failure_is_counted_and_logged():
    from ace_daemon import AceDaemon

    class FailingDeposition:
        def deposit_from_task(self, source, lexicon=None):
            raise RuntimeError("simulated retention failure")

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.experience_deposition = FailingDeposition()
    daemon.lexicon = None
    daemon.state = {}
    result = {
        "experiences_deposited": 0,
        "experience_deposition_failures": 0,
    }

    daemon._deposit_archived_experience(task("RQ-deposition-failure"), result)

    assert result == {
        "experiences_deposited": 0,
        "experience_deposition_failures": 1,
    }
    assert daemon.state["errors"][0]["module"] == "experience_deposition"
    assert daemon.state["errors"][0]["context"] == "RQ-deposition-failure"
    assert daemon.state["errors"][0]["error"] == "simulated retention failure"
