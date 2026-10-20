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


ESCALATIONS = [
    ("deposit_stall_experience.py", "stall-escalation"),
    ("deposit_selfref_experience.py", "selfref-escalation"),
]


def test_no_operational_script_writes_into_knowledge_bypassing_the_canonical_path():
    """A hand-built dict is a writer that looks like data.

    The first round of lane work asked which modules call deposit(), and found the
    four known windows. It missed these two entirely, because they call nothing -
    they build the record as a literal and write it with target.write_text(). The
    cost was not cosmetic: no lane, no entry in the deposition index, and a record
    find_related cannot reach. Only a direct-write test sees them.

    Tests are excluded: a test writing JSON into its own tmp_path is an isolated
    fixture, not a writer into the shared substrate.
    """
    from pathlib import Path
    import re

    ops_dir = Path(__file__).resolve().parent
    offenders = []
    for path in sorted(ops_dir.glob("*.py")):
        if path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        code = re.sub(r"(?m)^\s*#.*$", "", text)
        writes_directly = ("write_text(json.dumps" in code
                           or "write_text(\n        json.dumps" in code
                           or "write_bytes(" in code)
        # Narrowed to the substrate, but the *second* narrowing is what matters.
        # Flagging every write_text(json.dumps) named 21 scripts writing reports
        # and backups elsewhere. Flagging any mention of 09_KNOWLEDGE then named
        # backup_data.py, which reads the substrate and writes a manifest beside
        # the copy. A real writer names the substrate inside a write call - but the
        # earlier regex (write_text(...) with no ) before 09_KNOWLEDGE) missed the
        # joinpath form, ROOT.joinpath("09_KNOWLEDGE", ...).write_text(...), because
        # the ) of joinpath( breaks [^)\n]*. So: find the write call, then check the
        # rest of that physical line for the substrate name. A bypass that splits
        # the name across a line would slip by, which is acceptable for a guard.
        writes_to_substrate = any(
            re.search(r'(write_text|write_bytes|open|to_csv)\s*\(', line)
            and "09_KNOWLEDGE" in line
            for line in code.splitlines()
        )
        if writes_directly and writes_to_substrate and "deposition.deposit(" not in code and "deposit(task=" not in code:
            offenders.append(path.name)
    assert not offenders, (
        "these scripts write into 09_KNOWLEDGE as a hand-built dict, skipping the "
        f"lane, the index and the read side: {offenders}"
    )


@pytest.mark.parametrize("script,lane", ESCALATIONS)
def test_each_escalation_deposits_through_the_canonical_path(script, lane):
    """Run the real script against a throwaway tree and inspect what it wrote.

    Statically checking that the file mentions ExperienceDeposition is weaker than
    running it: the first fix produced a script that deposited correctly and then
    died on its own sha256 tail, pointing at the pre-canonical filename. Only a
    real run catches that the script does not actually succeed.
    """
    from pathlib import Path
    import re
    import subprocess
    import sys
    import tempfile

    repo = Path(__file__).resolve().parents[1]
    source = (repo / "ops" / script).read_text(encoding="utf-8")
    patched = re.sub(
        r'^ROOT = pathlib\.Path\(__file__\)\.resolve\(\)\.parent\.parent$',
        'ROOT = pathlib.Path(r"__SANDBOX__")', source, count=1, flags=re.M)
    assert patched != source, "could not redirect ROOT; refusing to run it live"

    with tempfile.TemporaryDirectory() as tmp:
        sandbox = Path(tmp) / "sandbox"
        (sandbox / "ops").mkdir(parents=True)
        runner = sandbox / "ops" / script
        runner.write_text(patched.replace("__SANDBOX__", str(sandbox)), encoding="utf-8")

        proc = subprocess.run([sys.executable, str(runner)],
                              capture_output=True, text=True, timeout=300,
                              encoding="utf-8", errors="replace")
        assert proc.returncode == 0, (
            f"{script} exited {proc.returncode}: {(proc.stderr or '')[:400]}"
        )
        assert "sha256" in (proc.stdout or ""), (
            f"{script} did not print its sha256: a script that dies after depositing "
            "reports failure for work it actually did"
        )

        knowledge = sandbox / "09_KNOWLEDGE"
        records = [p for p in knowledge.rglob("*.json") if p.name != "index.json"]
        assert len(records) == 1, f"{script} wrote {len(records)} records, expected 1"
        assert (knowledge / "index.json").is_file(), (
            "the canonical path updates the index; a hand-written dict never did"
        )

        data = json.loads(records[0].read_text(encoding="utf-8"))
        assert data["depositing_lane"] == lane
        assert data["constraints_updated"], "the constraints it recorded were lost"
        assert data["evidence"], "the evidence it recorded was lost"

        sys.path.insert(0, str(repo))
        from core.experience_deposition import ExperienceDeposition
        deposition = ExperienceDeposition(str(knowledge))
        found = deposition.find_related(data.get("conclusion", "")[:40], limit=5)
        assert found, "the record is on disk but unreachable by find_related"


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
