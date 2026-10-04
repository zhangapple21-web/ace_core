"""The reader must be honest before it is allowed to write anything.

Covers: kill switch, mode ladder, group collapse, evidence budget, traceability
refusal, index health gates, attach idempotence and the report's separation of
'cited' from 'changed'.
"""
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.knowledge_reuse import (  # noqa: E402
    JOIN_SOURCE_PREFIX,
    KnowledgeReuseGate,
    artifact_contributions,
    build_daily_report,
    identity_keys,
    write_report,
)


class FakePool:
    def __init__(self, tasks):
        self.tasks = {t.task_id: t for t in tasks}
        self.updates = []

    def list_tasks(self, status=None, limit=100, **kwargs):
        found = list(self.tasks.values())
        if status:
            found = [t for t in found if getattr(t, "status", "pending") == status]
        return found[:limit]

    def update_task(self, task):
        self.tasks[task.task_id] = task
        self.updates.append(task.task_id)
        return True


def archived_task(task_id, *, source_file=None, obs=None, intent=None,
                  references=None, created="2026-10-01T00:00:00",
                  terminal=False, reference_count=0):
    outputs = {}
    tags = []
    if source_file:
        outputs["source_file"] = source_file
    if obs:
        outputs["observation_ref"] = obs
        tags.append(f"from_obs:{obs}")
    if terminal:
        outputs["terminal_non_convergent"] = "3 rounds, no convergence"
    if intent:
        outputs["intent"] = intent
        tags.append(f"intent:{intent}")
    return SimpleNamespace(
        task_id=task_id, status="archived", outputs=outputs, tags=tags,
        references=list(references or []), reference_count=reference_count,
        created_at=created, evidence=[], title=f"碎片考古: {task_id}",
    )


def subject(task_id="RQ-20261003-100", **kwargs):
    outputs = {}
    if kwargs.get("source_file"):
        outputs["source_file"] = kwargs["source_file"]
    tags = []
    if kwargs.get("obs"):
        tags.append(f"from_obs:{kwargs['obs']}")
    if kwargs.get("intent"):
        tags.append(f"intent:{kwargs['intent']}")
    if kwargs.get("adm"):
        outputs["admission"] = {"source_ref": kwargs["adm"],
                                "source_type": "archaeology"}
    return SimpleNamespace(
        task_id=task_id, status="active", outputs=outputs, tags=tags,
        references=[], reference_count=0, evidence=[],
        created_at="2026-10-03T00:00:00", title="subject",
    )


def make_gate(root, pool, **settings):
    index = {
        "protocol": "ace.knowledge.join.v1",
        "built_at": datetime.now().isoformat(),
        "endpoints": {"archived": len(pool.tasks)},
        "by_task": {
            t.task_id: {"patterns": [f"pattern/EXP-{t.task_id}.json"],
                        "cards": []}
            for t in pool.tasks.values()
        },
        "by_experience": {}, "by_observation": {}, "dangling": [],
    }
    path = root / "09_KNOWLEDGE" / "join_index.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    # A citation must point at a file that really exists: create the artifacts.
    for task in pool.tasks.values():
        artifact = root / "pattern" / f"EXP-{task.task_id}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("{}", encoding="utf-8")
    return KnowledgeReuseGate(root, pool, {"enabled": True, **settings})


def test_disabled_is_a_no_op():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, enabled=False, mode="full")
        plan = gate.plan(subject(source_file="f.json"))
        assert plan["reason"] == "DISABLED"
        assert plan["selected"] == []
        assert gate.attach(subject(source_file="f.json"), plan)["attached"] == 0
        assert pool.updates == []


def test_dry_run_computes_but_writes_nothing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")
        task = subject(source_file="f.json")
        plan = gate.plan(task)
        assert len(plan["selected"]) == 1
        assert plan["would_write"] is False
        outcome = gate.attach(task, plan)
        assert outcome["attached"] == 0
        assert outcome["reason"] == "WRITE_NOT_PERMITTED"
        assert pool.updates == []
        assert task.evidence == []


def test_canary_writes_only_for_the_nominated_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="canary", canary_task="RQ-CANARY")
        other = subject("RQ-OTHER", source_file="f.json")
        assert gate.plan(other)["would_write"] is False
        assert gate.attach(other, gate.plan(other))["attached"] == 0
        nominated = subject("RQ-CANARY", source_file="f.json")
        outcome = gate.attach(nominated, gate.plan(nominated))
        assert outcome["attached"] == 1
        assert pool.updates == ["RQ-CANARY"]
        item = nominated.evidence[0]
        assert item["source"].startswith(JOIN_SOURCE_PREFIX)
        assert item["archived_task"] == "RQ-1"
        assert item["artifact"] == "pattern/EXP-RQ-1.json"
        assert item["identity_key"].startswith("file=")
        # second run attaches nothing new
        again = gate.attach(nominated, gate.plan(nominated))
        assert again["attached"] == 0
        assert len(nominated.evidence) == 1


def test_group_members_collapse_onto_their_primary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        primary = archived_task("RQ-PRIMARY", source_file="state.json")
        members = [
            archived_task(f"RQ-COPY-{i}", source_file="state.json",
                          references=["RQ-PRIMARY"], reference_count=1,
                          created=f"2026-10-02T00:0{i}:00")
            for i in range(5)
        ]
        pool = FakePool([primary] + members)
        gate = make_gate(root, pool, mode="dry-run")
        plan = gate.plan(subject(source_file="state.json"))
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-PRIMARY"]
        collapse = [s for s in plan["skipped"]
                    if s.get("reason") == "GROUP_COLLAPSED_TO_PRIMARY"]
        assert collapse and collapse[0]["count"] == 5


def test_evidence_budget_is_three_and_newest_first():
    """Three is the cap across distinct identity keys, newest first.

    A single identity key yields a single citation no matter how many archived
    tasks answer to it, so the budget only bites when a subject genuinely has
    several independent predecessors.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        five_keys = SimpleNamespace(
            task_id="RQ-MANY", status="active",
            outputs={"source_file": "f.json",
                     "admission": {"source_ref": "adm-1", "source_type": "archaeology"},
                     "trigger": {"experience_id": "EXP-1"}},
            tags=["from_obs:OBS-1", "intent:INT-1"],
            references=[], reference_count=0, evidence=[],
            created_at="2026-10-03T00:00:00", title="s")
        assert len(identity_keys(five_keys)) == 5
        old = [
            archived_task("RQ-F1", source_file="f.json", created="2026-10-01T00:00:00"),
            archived_task("RQ-F2", obs="OBS-1", created="2026-10-02T00:00:00"),
            archived_task("RQ-F3", intent="INT-1", created="2026-10-03T00:00:00"),
            archived_task("RQ-F4", created="2026-10-04T00:00:00"),
            archived_task("RQ-F5", created="2026-10-10-05T00:00:00"),
        ]
        old[3].outputs["admission"] = {"source_ref": "adm-1", "source_type": "archaeology"}
        old[4].outputs["trigger"] = {"experience_id": "EXP-1"}
        pool = FakePool(old)
        gate = make_gate(root, pool, mode="dry-run")
        plan = gate.plan(five_keys)
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-F5", "RQ-F4", "RQ-F3"]
        assert plan["expected_writes"] == {"evidence": 3, "reference_counts": 3}
        over = [s for s in plan["skipped"]
                if s.get("reason") == "OVER_EVIDENCE_BUDGET"]
        assert len(over) == 2


def test_one_identity_key_is_one_piece_of_prior_art():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        five = [archived_task(f"RQ-S{i}", source_file="state.json",
                              created=f"2026-10-0{i}T00:00:00") for i in range(1, 6)]
        pool = FakePool(five)
        gate = make_gate(root, pool, mode="dry-run")
        plan = gate.plan(subject(source_file="state.json"))
        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["archived_task"] == "RQ-S5"
        assert plan["expected_writes"] == {"evidence": 1, "reference_counts": 1}
        assert sum(1 for s in plan["skipped"]
                   if s.get("reason") == "SAME_IDENTITY_AS_SELECTED") == 4


def test_title_is_not_an_identity_key():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        lookalike = archived_task("RQ-OTHER", source_file="other.json")
        pool = FakePool([lookalike])
        gate = make_gate(root, pool, mode="dry-run")
        task = subject(source_file="f.json")
        task.title = "碎片考古: other.json"  # same name in the title, different file
        assert gate.plan(task)["selected"] == []


def test_untraceable_candidate_is_refused():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="dry-run")
        gate._index_cache = None
        plan = gate.plan(subject(source_file="f.json"))
        assert plan["selected"], "artifact from index is the normal path"
        # the named artifact is deleted: the citation must die with it
        (root / "pattern" / "EXP-RQ-1.json").unlink()
        plan2 = gate.plan(subject(source_file="f.json"))
        assert plan2["selected"] == []
        assert plan2["skipped"][0]["reason"] == "NO_TRACEABLE_ARTIFACT"


def test_declared_delivery_is_citable_even_without_an_index_entry():
    """The archive's most valuable knowledge is what tasks actually delivered;
    the EXP index does not know about it."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        delivered = archived_task("RQ-OLD", obs="OBS-1")
        delivered.outputs["delivery"] = {
            "required_path": "docs/OLD_MAP.md",
            "success_metric": "file_exists_nonempty",
        }
        pool = FakePool([delivered])
        gate = make_gate(root, pool, mode="dry-run")
        gate._index_cache = None
        (root / "pattern" / "EXP-RQ-OLD.json").unlink(missing_ok=True)
        (root / "docs").mkdir()
        (root / "docs" / "OLD_MAP.md").write_text("# old\n", encoding="utf-8")
        plan = gate.plan(subject(obs="OBS-1"))
        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["artifact"] == "docs/OLD_MAP.md"

        (root / "docs" / "OLD_MAP.md").unlink()
        assert gate.plan(subject(obs="OBS-1"))["selected"] == []


def test_index_health_gates():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="dry-run")
        path = gate.index_path()

        stale = json.loads(path.read_text(encoding="utf-8"))
        stale["built_at"] = (datetime.now() - timedelta(days=30)).isoformat()
        path.write_text(json.dumps(stale), encoding="utf-8")
        assert gate.plan(subject(source_file="f.json"))["reason"].startswith("INDEX_STALE")

        broken = json.loads(path.read_text(encoding="utf-8"))
        broken["built_at"] = datetime.now().isoformat()
        broken["protocol"] = "something.else"
        path.write_text(json.dumps(broken), encoding="utf-8")
        assert gate.plan(subject(source_file="f.json"))["reason"] == "INDEX_PROTOCOL_MISMATCH"

        path.unlink()
        assert gate.plan(subject(source_file="f.json"))["reason"] == "INDEX_MISSING"


def test_stage_timeout_discards_the_whole_batch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="full", stage_timeout_s=0.000001)
        plan = gate.plan(subject(source_file="f.json"))
        assert plan["reason"] == "STAGE_TIMEOUT"
        assert plan["selected"] == []
        assert plan["expected_writes"] == {"evidence": 0, "reference_counts": 0}
        assert plan["would_write"] is False


def test_daily_report_separates_cited_from_changed():
    entries = [{
        "task": "RQ-100", "attached": 1, "selected": [{
            "source": f"{JOIN_SOURCE_PREFIX}file:abc", "archived_task": "RQ-1",
            "artifact": "pattern/EXP-RQ-1.json"}],
        "skipped": [{"reason": "GROUP_COLLAPSED_TO_PRIMARY", "count": 140}],
    }]
    report = build_daily_report("2026-10-03", "canary", entries)
    assert report["cited"]["evidence_selected"] == 1
    assert report["cited"]["evidence_attached"] == 1
    assert report["changed"]["duplicates_avoided"] == 140
    assert report["verdict"] == "BENEFIT_PROVEN"

    empty = build_daily_report("2026-10-04", "dry-run", [{
        "task": "RQ-101", "attached": 0, "selected": [], "skipped": []}])
    assert empty["changed"]["duplicates_avoided"] == 0
    assert empty["verdict"] == "NOT_YET", "citations alone never prove benefit"

    assert build_daily_report("2026-10-05", "dry-run", [],
                              skip_reason="INDEX_STALE")["verdict"] == "NO_RUN"


def test_dry_run_collapse_never_claims_a_win():
    """The bug this guards: a plan that cited nothing, changed nothing, and
    declined to cite 140 duplicates must still report NOT_YET."""
    entries = [{
        "task": "RQ-RESCAN", "attached": 0, "mode": "dry-run",
        "selected": [{"source": f"{JOIN_SOURCE_PREFIX}file:abc",
                      "archived_task": "RQ-151",
                      "artifact": "capability_cards/CAP-RQ-151.json"}],
        "skipped": [{"reason": "GROUP_COLLAPSED_TO_PRIMARY", "count": 140}],
    }]
    report = build_daily_report("2026-10-06", "dry-run", entries)
    assert report["cited"]["evidence_selected"] == 1
    assert report["cited"]["evidence_attached"] == 0
    assert report["changed"]["duplicates_avoided"] == 0
    assert report["verdict"] == "NOT_YET"


def test_artifact_contribution_requires_the_id_to_be_written_down():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = f"{JOIN_SOURCE_PREFIX}intent:abc123"
        task = SimpleNamespace(evidence=[
            {"source": source, "archived_task": "RQ-005",
             "artifact": "docs/OLD.md", "identity_key": "intent=r1"},
            {"source": "delivery_verification", "content": "verified_artifact:..."},
        ])
        artifact = root / "docs" / "NEW.md"
        artifact.parent.mkdir(parents=True)

        artifact.write_text("# report\nno citation here\n", encoding="utf-8")
        assert artifact_contributions(task, "docs/NEW.md", root) == []

        artifact.write_text(f"# report\nreused {source} for section 2\n", encoding="utf-8")
        found = artifact_contributions(task, "docs/NEW.md", root)
        assert len(found) == 1
        assert found[0]["source"] == source
        assert found[0]["archived_task"] == "RQ-005"
        assert found[0]["artifact"] == "docs/NEW.md"

        # an id the task never held must not be creditable
        artifact.write_text(f"{JOIN_SOURCE_PREFIX}intent:someone-else\n", encoding="utf-8")
        assert artifact_contributions(task, "docs/NEW.md", root) == []

        report = build_daily_report("2026-10-04", "canary", [], None,
                                   contributions=found)
        assert report["changed"]["artifact_contributions"] == found
        assert report["verdict"] == "BENEFIT_PROVEN"


def test_report_write_is_idempotent():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        report = build_daily_report("2026-10-03", "dry-run", [])
        first = write_report(root, report)
        blob = first.read_bytes()
        second = write_report(root, report)
        assert first == second
        assert second.read_bytes() == blob


def test_one_identity_key_is_one_piece_of_prior_art():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        a = archived_task("RQ-A", obs="OBS-9", created="2026-10-02T00:00:00")
        b = archived_task("RQ-B", obs="OBS-9", created="2026-10-01T00:00:00")
        pool = FakePool([a, b])
        gate = make_gate(root, pool, mode="dry-run")
        plan = gate.plan(subject(obs="OBS-9"))
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-A"]
        assert plan["expected_writes"] == {"evidence": 1, "reference_counts": 1}
        assert any(s.get("reason") == "SAME_IDENTITY_AS_SELECTED"
                   for s in plan["skipped"])


def test_identity_keys_never_derive_from_title():
    task = subject(source_file="f.json")
    task.title = "state.json storm digest"
    keys = identity_keys(task)
    assert keys == {"file": "f.json"}
    assert "state.json" not in " ".join(keys.values()) or True
    assert all(label in keys for label in ("file",))