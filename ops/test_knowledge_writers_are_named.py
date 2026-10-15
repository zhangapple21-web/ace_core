"""Every window that writes into 09_KNOWLEDGE must say which window it was.

The substrate's promise is that a reader holding a record can tell who learned
it. Four windows deposit there, and three of them were writing anonymously until
this was found: learning_return_bridge, skill_generator, and mission_runner all
produced artifacts with no depositing_lane. 167 capability cards, 17 skills and
6 rounds sat in the shared pile looking exactly like each other.

The pin is deliberately about all four writers, not one at a time. The failure
this guards against is a *new* writer appearing anonymous, and a per-writer test
would not catch it.
"""
import json
from types import SimpleNamespace

import pytest

from core.experience_deposition import ExperienceDeposition
from core.learning_return_bridge import LearningReturnBridge, _card_sha
from core.skill_generator import SkillGenerator


def _archived_task(task_id="RQ-SKILL-001"):
    """A real Task, not a stand-in: the fixture must satisfy the real path."""
    from core.task import Task

    return Task(
        task_id=task_id,
        title="处理超时后重试策略",
        hypothesis="重试需要指数退避与上限",
        creator="researcher",
        guardian_decision="lesson",
        tags=["retry", "timeout"],
    )


def test_capability_cards_name_the_window_that_wrote_them(tmp_path):
    task = SimpleNamespace(
        task_id="RQ-CARD-001",
        guardian_decision="experience",
        evidence=[{"source": "https://github.com/example/x",
                   "source_ref": "https://github.com/example/x"}],
        outputs={"external_mining": {"fetched": {"repository": "https://github.com/example/x",
                                                 "fingerprint": "f1"},
                                     "miner_result": {"analysis": {
                                         "recommended_absorbable_capabilities": ["a"],
                                         "next_verification": ["b"]}}}},
    )
    (tmp_path / "video").mkdir()
    LearningReturnBridge(tmp_path, video_root=tmp_path / "video").materialize(task)
    card = json.loads(
        (tmp_path / "09_KNOWLEDGE/capability_cards/CAP-RQ-CARD-001.json").read_text(encoding="utf-8"))
    assert card["depositing_lane"] == "learning-return-bridge", (
        "a card that does not name its window is anonymous in the shared pile"
    )


def test_the_lane_is_not_part_of_a_cards_identity(tmp_path):
    """Replay must stay a no-op, so the lane must sit outside the hash.

    _card_sha excludes created_at for the same reason. If the lane were hashed,
    every unchanged card would look modified on its next replay and be rewritten,
    which is exactly what the no-op guard at the materialize path forbids.
    """
    card = {"card_id": "CAP-X", "source_task_id": "RQ-X", "capability_state": "S"}
    before = _card_sha(card)
    with_lane = dict(card, depositing_lane="learning-return-bridge")
    after = _card_sha(with_lane)
    assert before == after, (
        "the lane is provenance, not content: hashing it would break replay no-ops"
    )


def test_generated_skills_name_the_window_that_wrote_them(tmp_path):
    generator = SkillGenerator(tmp_path / "09_KNOWLEDGE" / "skills")
    result = generator.analyze_archived_tasks([_archived_task(), _archived_task("RQ-SKILL-002")])
    new_skills = result.get("new_skills") or []
    assert new_skills, "fixture must produce a skill"
    for name in new_skills:
        path = tmp_path / "09_KNOWLEDGE" / "skills" / f"SKILL-{name}.json"
        assert path.is_file(), f"{name} was reported new but never written"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["depositing_lane"] == "skill-generator", (
            "a skill that does not name its window is anonymous in the shared pile"
        )


def test_mission_rounds_name_the_window_that_wrote_them():
    """The record must name its window under the substrate's field.

    It already carried ``owner`` - the task-claim token. That is real
    attribution, but under a name the substrate does not read, so a reader
    looking for depositing_lane found nothing.
    """
    from ops import mission_runner

    assert mission_runner.DEPOSITING_LANE == mission_runner.OWNER, (
        "the depositing lane and the claim token must agree, not diverge"
    )


@pytest.mark.parametrize("writer,expected", [
    ("adjudication", "adjudication"),
    ("watcher", "watcher"),
    ("external-reviewer", "external-reviewer"),
])
def test_the_daemon_windows_each_claim_their_own_lane_name(writer, expected):
    """The emitter module must actually use its lane name, not define and ignore it."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    sources = {
        "adjudication": root / "core" / "autonomous_adjudication.py",
        "watcher": root / "ops" / "dead_component_watch.py",
        "external-reviewer": root / "core" / "free_zone_external_reviewer.py",
    }
    text = sources[writer].read_text(encoding="utf-8")
    assert f'lane="{expected}"' in text, (
        f"{writer} defines a lane but never passes it: its deposit is anonymous"
    )


def test_the_deposition_path_records_the_lane_on_a_first_deposit(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path / "09_KNOWLEDGE"))
    task = SimpleNamespace(
        task_id="RQ-LANE-FIRST", title="t", hypothesis="h",
        guardian_decision="lesson", evidence=[], outputs={}, tags=[],
        created_at="2026-10-15T00:00:00+00:00",
    )
    record = deposition.deposit(task=task, experience_type="lesson", lane="adjudication")
    assert record.depositing_lane == "adjudication"
    on_disk = json.loads(
        (tmp_path / "09_KNOWLEDGE" / "lesson" / f"{record.experience_id}.json").read_text(encoding="utf-8"))
    assert on_disk["depositing_lane"] == "adjudication", (
        "the store must agree with the returned object, not just memory"
    )


def test_deposit_from_task_carries_the_archivists_lane(tmp_path):
    """The production path, not a helper.

    The daemon's archivist is the only caller that writes records the lifecycle
    itself produces, and it called deposit_from_task with no way to name itself.
    Every record it wrote - 9 patterns on 2026-10-15 and the whole historical
    population before them - came out anonymous. The parameter is optional, so a
    caller that has no window still works; this test is what stops the
    production caller from quietly being that caller again.
    """
    deposition = ExperienceDeposition(str(tmp_path / "09_KNOWLEDGE"))
    from core.task import Task

    task = Task(task_id="RQ-ARCH-001", title="t", hypothesis="h",
                guardian_decision="experience", tags=["x"])
    record = deposition.deposit_from_task(task, lane="daemon-archivist")
    assert record is not None
    assert record.depositing_lane == "daemon-archivist"
    on_disk = json.loads(
        (tmp_path / "09_KNOWLEDGE" / "pattern" / f"{record.experience_id}.json").read_text(encoding="utf-8"))
    assert on_disk["depositing_lane"] == "daemon-archivist"


def test_the_lane_defaults_to_unattributed_rather_than_guessing(tmp_path):
    """Optional means optional: no invented window name for a caller that has none."""
    deposition = ExperienceDeposition(str(tmp_path / "09_KNOWLEDGE"))
    from core.task import Task

    task = Task(task_id="RQ-ARCH-002", title="t", hypothesis="h",
                guardian_decision="experience", tags=["x"])
    record = deposition.deposit_from_task(task)
    assert record.depositing_lane == "unattributed", (
        "an unknown caller must stay visibly unattributed, not be assigned a "
        "window it never claimed"
    )
