"""The join index must be rebuildable from the authoritative stores without
triggering TaskPool runtime recovery side effects.

``core/knowledge_reuse.py`` trusts ``09_KNOWLEDGE/join_index.v1.json``
completely: a missing, stale, or wrong index makes the reuse stage plan nothing,
with no error. Nothing else in the tree builds it, so it silently froze and no
real task could reach graded knowledge. These tests pin the builder that closes
that hole.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.knowledge_reuse import INDEX_PROTOCOL, KnowledgeReuseGate  # noqa: E402
from core.task import TaskPool  # noqa: E402
from build_knowledge_join_index import build, main  # noqa: E402

DERIVED = {
    "axiom": "VERIFIED_FACT",
    "constraint": "RULE",
    "pattern": "EVIDENCE",
    "lesson": "COUNTEREXAMPLE",
    "observation": "OBSERVATION",
}


def _set_builder_paths(builder, root, knowledge, pool):
    builder.ROOT = root
    builder.KNOWLEDGE = knowledge
    builder.INDEX_PATH = knowledge / "join_index.v1.json"
    builder.KNOWLEDGE_INDEX = knowledge / "index.json"
    builder.POOL = pool


def _archive(pool, task_id, outputs, evidence=0):
    task = pool.create_task(
        "owner", hypothesis="h", creator="test",
        admission={
            "source_type": "archaeology", "source_ref": f"ref-{task_id}",
            "why_now": "w", "evidence": [{"source": "s", "content": "c"}],
            "expected_result": "e", "verification_method": "v",
            "risk": "r", "estimated_scope": "one",
        },
        outputs=outputs,
        data_class="CAPABILITY",
    )
    for i in range(evidence):
        task.add_evidence(f"fact {i}", source=f"s{i}")
    pool.move_task(task.task_id, "active", actor="test")
    pool.move_task(task.task_id, "review", actor="test")
    pool.move_task(task.task_id, "approved", actor="test")
    task = pool.load_task(task.task_id)
    task.guardian_decision = "experience"
    pool.update_task(task)
    pool.move_task(task.task_id, "archived", actor="test")
    return task.task_id


def _write_record(knowledge, experience_id, source_task, experience_type,
                  epistemic_status=None):
    (knowledge / experience_type).mkdir(parents=True, exist_ok=True)
    path = knowledge / experience_type / f"{experience_id}.json"
    payload = {
        "experience_id": experience_id,
        "source_task_id": source_task,
        "experience_type": experience_type,
        "conclusion": f"{experience_type} conclusion for {source_task}",
        "evidence": [], "constraints_updated": [], "related_concepts": [],
        "tags": [experience_type], "data_class": "PRIVATE",
        "created_at": "2026-01-01T00:00:00",
        "reference_count": 0, "last_used_at": "2026-01-01T00:00:00",
    }
    if epistemic_status:
        payload["epistemic_status"] = epistemic_status
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _knowledge_index(knowledge, records):
    (knowledge / "index.json").write_text(json.dumps({
        record.stem: {
            "path": str(record),
            "type": record.parent.name,
            "conclusion": record.stem,
            "source_task": "",
        }
        for record in records
    }), encoding="utf-8")


def test_build_indexes_archived_records_and_grades_them(tmp_path, monkeypatch):
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    knowledge.mkdir(parents=True)
    pool = TaskPool(str(root / "task_pool"))
    _set_builder_paths(builder, root, knowledge, pool)

    archived = _archive(pool, "RQ-ARCHIVED",
                        {"source_file": "C:/frag/a.md"})
    rule = _write_record(knowledge, "EXP-RULE-1", archived, "constraint")
    pattern = _write_record(knowledge, "EXP-PAT-1", archived, "pattern")
    _knowledge_index(knowledge, [rule, pattern])

    payload = build()

    assert payload["protocol"] == INDEX_PROTOCOL
    assert archived in payload["by_task"]
    assert rule.as_posix() in payload["by_task"][archived]["patterns"]
    # A pre-merge constraint record has no field; the grade must still resolve.
    assert payload["endpoints"]["by_epistemic_status"]["RULE"] == 1
    assert payload["endpoints"]["by_epistemic_status"]["EVIDENCE"] == 1
    assert payload["endpoints"]["dangling"] == 0


def test_build_drops_records_whose_task_is_not_archived(tmp_path, monkeypatch):
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    knowledge.mkdir(parents=True)
    pool = TaskPool(str(root / "task_pool"))
    _set_builder_paths(builder, root, knowledge, pool)

    # A task that is still pending must never be advertised as reusable history.
    live = pool.create_task(
        "in flight", hypothesis="h", creator="test",
        admission={
            "source_type": "archaeology", "source_ref": "ref-live",
            "why_now": "w", "evidence": [{"source": "s", "content": "c"}],
            "expected_result": "e", "verification_method": "v",
            "risk": "r", "estimated_scope": "one",
        },
    )
    live_record = _write_record(knowledge, "EXP-LIVE-1", live.task_id, "pattern")
    _knowledge_index(knowledge, [live_record])

    payload = build()

    assert live.task_id not in payload["by_task"]
    assert payload["endpoints"]["dropped_not_archived"] == 1


def test_build_reports_a_record_whose_file_vanished(tmp_path, monkeypatch):
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    knowledge.mkdir(parents=True)
    pool = TaskPool(str(root / "task_pool"))
    _set_builder_paths(builder, root, knowledge, pool)

    (knowledge / "index.json").write_text(json.dumps({
        "EXP-GONE": {"path": str(knowledge / "pattern" / "EXP-GONE.json"),
                     "type": "pattern", "conclusion": "x", "source_task": ""},
    }), encoding="utf-8")

    payload = build()

    assert payload["endpoints"]["dangling"] == 1
    assert payload["dangling"][0]["id"] == "EXP-GONE"


def test_importing_builder_does_not_construct_task_pool(monkeypatch):
    import importlib
    import core.task as task_module
    import build_knowledge_join_index as builder

    original = task_module.TaskPool

    def forbid_task_pool(*args, **kwargs):
        raise AssertionError("builder import must not construct TaskPool")

    monkeypatch.setattr(task_module, "TaskPool", forbid_task_pool)
    try:
        builder = importlib.reload(builder)
    finally:
        monkeypatch.setattr(task_module, "TaskPool", original)
        importlib.reload(builder)

    assert builder.POOL is None


def test_builder_does_not_construct_task_pool_or_recover_runtime_state(tmp_path, monkeypatch):
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    archived_dir = root / "task_pool" / "archived"
    knowledge.mkdir(parents=True)
    archived_dir.mkdir(parents=True)
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(builder, "KNOWLEDGE_INDEX", knowledge / "index.json")
    monkeypatch.setattr(builder, "POOL", None)

    archived_task = archived_dir / "RQ-ARCHIVED.json"
    archived_task.write_text(json.dumps({
        "task_id": "RQ-ARCHIVED", "status": "archived",
    }), encoding="utf-8")
    # A conflicting temp file is recovery input, not builder-owned state. The
    # read-only builder must leave it byte-for-byte intact.
    duplicate = root / "task_pool" / "pending" / "RQ-ARCHIVED.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(json.dumps({
        "task_id": "RQ-ARCHIVED", "status": "pending",
    }), encoding="utf-8")
    temp_file = archived_dir / "RQ-ORPHAN.json.tmp"
    temp_file.write_text("keep-me", encoding="utf-8")
    record = _write_record(knowledge, "EXP-ARCHIVED", "RQ-ARCHIVED", "pattern")
    _knowledge_index(knowledge, [record])

    payload = builder.build()

    assert "RQ-ARCHIVED" in payload["by_task"]
    assert duplicate.is_file()
    assert temp_file.read_text(encoding="utf-8") == "keep-me"
    assert not (root / "task_pool" / "task_index.json").exists()


def test_a_rebuilt_index_lets_the_real_gate_match_a_graded_record(tmp_path):
    """The point of the index: without it the reuse stage plans nothing."""
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    knowledge.mkdir(parents=True)
    pool = TaskPool(str(root / "task_pool"))
    monkeypatch_targets = {
        "ROOT": root, "KNOWLEDGE": knowledge,
        "INDEX_PATH": knowledge / "join_index.v1.json",
        "KNOWLEDGE_INDEX": knowledge / "index.json", "POOL": pool,
    }
    original = {k: getattr(builder, k) for k in monkeypatch_targets}
    for key, value in monkeypatch_targets.items():
        setattr(builder, key, value)
    try:
        source = "C:/frag/identity.md"
        archived = _archive(pool, "RQ-ARCHIVED", {"source_file": source})
        prior = pool.load_task(archived)
        receipt = {
            "schema_version": 1,
            "status": "VERIFIED",
            "task_id": archived,
            "verified_at": "2026-10-01T00:00:00",
            "verifier": "fixture_independent_verifier",
            "result_ref": f"fixture://{archived}/result",
            "verification_ref": f"fixture://{archived}/verification",
            "evidence_refs": [f"fixture://{archived}/e0",
                              f"fixture://{archived}/e1"],
            "independent_evidence_groups": 2,
        }
        prior.outputs["verified_outcome_receipt"] = receipt
        pool.update_task(prior)
        rule = _write_record(knowledge, "EXP-RULE", archived, "constraint",
                             epistemic_status="RULE")
        record = json.loads(rule.read_text(encoding="utf-8"))
        record["data_class"] = "CAPABILITY"
        record["verification"] = {
            key: receipt[key] for key in (
                "status", "verified_at", "verifier", "result_ref",
                "verification_ref", "evidence_refs",
                "independent_evidence_groups",
            )
        }
        rule.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        archived_record = pool.load_task(archived)
        archived_record.guardian_decision = "constraint"
        pool.update_task(archived_record)
        _knowledge_index(knowledge, [rule])
        builder.main()
    finally:
        for key, value in original.items():
            setattr(builder, key, value)

    subject = pool.create_task(
        "new work", hypothesis="h", creator="test",
        admission={
            "source_type": "archaeology", "source_ref": source,
            "why_now": "w", "evidence": [{"source": "s", "content": "c"}],
            "expected_result": "e", "verification_method": "v",
            "risk": "r", "estimated_scope": "one",
        },
        outputs={"source_file": source},
        data_class="CAPABILITY",
    )

    gate = KnowledgeReuseGate(root, pool, {"enabled": True, "mode": "full",
                                           "index_path": "09_KNOWLEDGE/join_index.v1.json"})
    plan = gate.plan(pool.load_task(subject.task_id))

    assert len(plan["selected"]) == 1
    assert plan["selected"][0]["source"].startswith("knowledge_join:")
    assert plan["selected"][0]["archived_task"] == archived
    assert Path(plan["selected"][0]["artifact"]).name == rule.name


def test_rebuilt_index_passes_the_gate_freshness_check(tmp_path, monkeypatch):
    """A freshly built index must not be rejected as stale on the next cycle."""
    import build_knowledge_join_index as builder

    root = tmp_path / "ace_core"
    knowledge = root / "09_KNOWLEDGE"
    knowledge.mkdir(parents=True)
    pool = TaskPool(str(root / "task_pool"))
    _set_builder_paths(builder, root, knowledge, pool)

    (knowledge / "index.json").write_text("{}", encoding="utf-8")
    builder.main()

    gate = KnowledgeReuseGate(root, pool, {"enabled": True,
                                           "index_path": "09_KNOWLEDGE/join_index.v1.json"})
    loaded, status = gate.load_index()

    assert status == "OK"
    assert loaded["protocol"] == INDEX_PROTOCOL
    built = datetime.fromisoformat(loaded["built_at"])
    assert built > datetime.now() - timedelta(minutes=5)