"""The daemon hook must be inert by default and honest when it does run.

Constructing a real AceDaemon is the point: the gate is wired in __init__, so a
test with a stubbed gate would prove nothing about the wiring.
"""
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace_daemon import AceDaemon  # noqa: E402
from core.task import TaskPool  # noqa: E402


def _index(root: Path, task_ids) -> None:
    path = root / "09_KNOWLEDGE" / "join_index.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "protocol": "ace.knowledge.join.v1",
        "built_at": datetime.now().isoformat(),
        "endpoints": {"archived": len(task_ids)},
        "by_task": {t: {"patterns": [f"pattern/EXP-{t}.json"], "cards": []}
                    for t in task_ids},
        "by_experience": {}, "by_observation": {}, "dangling": [],
    }), encoding="utf-8")
    # The reader refuses to cite an artifact that is not really on disk, so the
    # fixture has to own the files it advertises.
    for task_id in task_ids:
        artifact = root / "pattern" / f"EXP-{task_id}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("{}", encoding="utf-8")


def _archive(pool, task_id):
    active = pool.move_task(task_id, "active", actor="test")
    review = pool.move_task(task_id, "review", actor="test", task=active)
    approved = pool.move_task(task_id, "approved", actor="test", task=review)
    archived = pool.move_task(task_id, "archived", actor="test", task=approved)
    assert archived is not None
    return archived


def _add_subject(pool, material, ref):
    return pool.create_task(
        "subject", creator="test",
        admission={
            "source_type": "archaeology", "source_ref": ref,
            "why_now": "new work", "evidence": [{"source": "s", "risk": "low"}],
            "expected_result": "read it", "verification_method": "re-read",
            "risk": "read-only", "estimated_scope": "one file",
        },
        outputs={"source_file": str(material)},
    )


def _seeded_daemon(root: Path, settings):
    pool = TaskPool(str(root / "task_pool"))
    material = root / "material.md"
    material.write_text("# material\n", encoding="utf-8")
    from core.file_scanner import FileScanner

    scanner = FileScanner(pool, None, [])
    fingerprint = scanner._content_fingerprint(material)
    old = pool.create_task(
        "内部材料考古: material.md", creator="local_archaeologist",
        admission={
            "source_type": "archaeology", "source_ref": str(material),
            "source_fingerprint": fingerprint, "why_now": "old work",
            "evidence": [{"source": str(material), "risk": "low"}],
            "expected_result": "read it", "verification_method": "re-read",
            "risk": "read-only", "estimated_scope": "one file",
        },
        outputs={"source_file": str(material),
                 "source_fingerprint": fingerprint},
    )
    assert _archive(pool, old.task_id)
    _index(root, [old.task_id])

    subject = _add_subject(pool, material, "subject-1")
    daemon = AceDaemon(root, {"runtime": {"knowledge_reuse": settings}})
    return daemon, pool, subject


def test_switch_defaults_to_off_and_touches_nothing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {})
        result = {}
        entry = daemon._run_knowledge_reuse_stage(subject, result)
        assert entry["reason"] == "DISABLED"
        assert entry["selected"] == []
        assert pool.load_task(subject.task_id).evidence == []
        assert result["knowledge_reuse"][0]["attached"] == 0


def test_dry_run_plans_reports_and_writes_no_evidence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {"enabled": True,
                                                       "mode": "dry-run"})
        result = {}
        entry = daemon._run_knowledge_reuse_stage(subject, result)
        assert entry["reason"] is None
        assert len(entry["selected"]) == 1
        assert entry["selected"][0]["source"].startswith("knowledge_join:")
        assert entry["attached"] == 0
        assert entry["attach_reason"] == "DRY_RUN"
        assert pool.load_task(subject.task_id).evidence == []

        path = daemon._write_knowledge_reuse_report(result)
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["verdict"] == "NOT_YET", report
        assert report["cited"]["evidence_selected"] == 1
        assert report["cited"]["evidence_attached"] == 0
        assert report["changed"]["artifact_contributions"] == []
        assert daemon.state["cycle_progress"]["knowledge_reuse"]["mode"] == "dry-run"

        blob = path.read_bytes()
        daemon._write_knowledge_reuse_report(result)
        assert path.read_bytes() == blob, "rerunning a day must rewrite, not append"


def test_canary_attaches_traceable_evidence_only_for_its_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {
            "enabled": True, "mode": "canary", "canary_task": "RQ-SOMEONE-ELSE"})
        result = {}
        entry = daemon._run_knowledge_reuse_stage(subject, result)
        assert entry["selected"], "the plan is computed regardless of mode"
        assert entry["attached"] == 0, "not the nominated task: no write"
        assert pool.load_task(subject.task_id).evidence == []

        daemon.knowledge_reuse.settings["canary_task"] = subject.task_id
        entry2 = daemon._run_knowledge_reuse_stage(subject, result)
        assert entry2["attached"] == 1
        persisted = pool.load_task(subject.task_id)
        item = persisted.evidence[-1]
        assert item["source"].startswith("knowledge_join:")
        assert item["archived_task"] and item["artifact"] and item["identity_key"]
        assert item["read_only"] is True

        again = daemon._run_knowledge_reuse_stage(subject, result)
        assert again["attached"] == 0, "same source must not attach twice"
        assert len(pool.load_task(subject.task_id).evidence) == len(persisted.evidence)


def test_daily_budget_stops_attaching():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {
            "enabled": True, "mode": "full", "budget_evidence_per_day": 1})
        first = daemon._run_knowledge_reuse_stage(subject, {})
        assert first["attached"] == 1
        # A different task on the same source still wants the same evidence.
        second_task = _add_subject(pool, root / "material.md", "subject-2")
        second = daemon._run_knowledge_reuse_stage(second_task, {})
        assert second["selected"], "nothing was selected, so this proves nothing"
        assert second["attached"] == 0
        assert second["attach_reason"] == "DAILY_BUDGET_EXHAUSTED"
        assert pool.load_task(second_task.task_id).evidence == []


def test_verified_delivery_records_the_reuse_contribution():
    """The acceptance path, end to end and without a model call.

    A task that was handed archived knowledge, produced an artifact that cites
    the knowledge_join id, and got its declared delivery verified must show up
    in the report as a contribution. If this wiring is ever removed the verdict
    silently drops back to NOT_YET, which is exactly the failure this test is
    here to make loud.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {"enabled": True,
                                                       "mode": "canary",
                                                       "canary_task": "RQ-CANARY"})
        daemon.knowledge_reuse.settings["canary_task"] = subject.task_id
        entry = daemon._run_knowledge_reuse_stage(subject, {})
        assert entry["attached"] == 1
        source = entry["selected"][0]["source"]

        artifact = root / "docs" / "DELIVERED.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f"# delivered\nreused {source}\n", encoding="utf-8")
        delivered = pool.load_task(subject.task_id)
        delivered.outputs["delivery"] = {
            "required_path": "docs/DELIVERED.md",
            "success_metric": "file_exists_nonempty",
            "domain": "analysis",
        }
        assert pool.update_task(delivered)
        assert pool.move_task(subject.task_id, "active", actor="test",
                              task=pool.load_task(subject.task_id))
        assert pool.move_task(subject.task_id, "review", actor="test",
                              task=pool.load_task(subject.task_id))

        result = {}
        daemon._run_declared_deliveries(result)
        assert result["delivery_execution"]["delivered"] >= 1
        assert daemon._knowledge_reuse_contributions, (
            "verified delivery did not record the reuse contribution"
        )
        contribution = daemon._knowledge_reuse_contributions[0]
        assert contribution["source"] == source
        assert contribution["artifact"] == "docs/DELIVERED.md"

        path = daemon._write_knowledge_reuse_report(result)
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["changed"]["artifact_contributions"] == [
            daemon._knowledge_reuse_contributions[0]]
        assert report["verdict"] == "BENEFIT_PROVEN"
        assert daemon.state["cycle_progress"]["knowledge_reuse"][
            "artifact_contributions"] == 1


def test_missing_index_is_a_skip_not_a_write():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daemon, pool, subject = _seeded_daemon(root, {"enabled": True,
                                                       "mode": "full"})
        (root / "09_KNOWLEDGE" / "join_index.v1.json").unlink()
        daemon.knowledge_reuse._index_cache = None
        entry = daemon._run_knowledge_reuse_stage(subject, {})
        assert entry["reason"] == "INDEX_MISSING"
        assert entry["attached"] == 0
        assert pool.load_task(subject.task_id).evidence == []