"""The join index must be rebuildable from the authoritative stores.

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
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(builder, "INDEX_PATH", knowledge / "join_index.v1.json")
    monkeypatch.setattr(builder, "KNOWLEDGE_INDEX", knowledge / "index.json")
    monkeypatch.setattr(builder, "POOL", pool)

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
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(builder, "INDEX_PATH", knowledge / "join_index.v1.json")
    monkeypatch.setattr(builder, "KNOWLEDGE_INDEX", knowledge / "index.json")
    monkeypatch.setattr(builder, "POOL", pool)

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
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "KNOWLEDGE", knowledge)
    monkeypatch.setattr(builder, "INDEX_PATH", knowledge / "join_index.v1.json")
    monkeypatch.setattr(builder, "KNOWLEDGE_INDEX", knowledge / "index.json")
    monkeypatch.setattr(builder, "POOL", pool)

    (knowledge / "index.json").write_text(json.dumps({
        "EXP-GONE": {"path": str(knowledge / "pattern" / "EXP-GONE.json"),
                     "type": "pattern", "conclusion": "x", "source_task": ""},
    }), encoding="utf-8")

    payload = build()

    assert payload["endpoints"]["dangling"] == 1
    assert payload["dangling"][0]["id"] == "EXP-GONE"


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
        rule = _write_record(knowledge, "EXP-RULE", archived, "constraint")
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
    for key, value in {"ROOT": root, "KNOWLEDGE": knowledge,
                       "INDEX_PATH": knowledge / "join_index.v1.json",
                       "KNOWLEDGE_INDEX": knowledge / "index.json",
                       "POOL": pool}.items():
        monkeypatch.setattr(builder, key, value)

    (knowledge / "index.json").write_text("{}", encoding="utf-8")
    builder.main()

    gate = KnowledgeReuseGate(root, pool, {"enabled": True,
                                           "index_path": "09_KNOWLEDGE/join_index.v1.json"})
    loaded, status = gate.load_index()

    assert status == "OK"
    assert loaded["protocol"] == INDEX_PROTOCOL
    built = datetime.fromisoformat(loaded["built_at"])
    assert built > datetime.now() - timedelta(minutes=5)