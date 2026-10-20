"""The Governor's dedup search must observe the real Knowledge store.

``Governor._search_existing_knowledge`` is the existing "search before add"
mechanism that keeps Knowledge from duplicating.  It used to read
``09_KNOWLEDGE/experiences.json`` and a doubled ``06_RUNTIME/ace/`` prefix,
neither of which any writer creates, so every candidate looked novel.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.governance.knowledge_governor import Governor  # noqa: E402


def _seed(root: Path, conclusion: str, experience_id: str = "EXP-SEED-1") -> Path:
    knowledge = root / "09_KNOWLEDGE"
    (knowledge / "pattern").mkdir(parents=True)
    record = {
        "experience_id": experience_id,
        "source_task_id": "RQ-SEED",
        "experience_type": "pattern",
        "conclusion": conclusion,
        "evidence": [],
        "constraints_updated": [],
        "related_concepts": [],
        "tags": ["pattern"],
        "data_class": "PRIVATE",
        "created_at": "2026-01-01T00:00:00",
        "reference_count": 0,
        "last_used_at": "2026-01-01T00:00:00",
    }
    path = knowledge / "pattern" / f"{experience_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    (knowledge / "index.json").write_text(
        json.dumps({
            experience_id: {
                "path": str(path),
                "type": "pattern",
                "conclusion": conclusion[:100],
                "source_task": "RQ-SEED",
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def test_resolves_the_canonical_root_from_a_runtime_subdirectory(tmp_path):
    (tmp_path / "09_KNOWLEDGE").mkdir()
    (tmp_path / "08_GOVERNANCE").mkdir()
    runtime_subdir = tmp_path / "06_RUNTIME" / "ace"
    runtime_subdir.mkdir(parents=True)

    governor = Governor(str(runtime_subdir))

    root = tmp_path.resolve()
    assert governor.ace_runtime_dir == root
    assert governor.knowledge_records_file == (
        root / "08_GOVERNANCE" / "governor" / "knowledge_governor_records.jsonl"
    )
    assert governor.knowledge_index_file == root / "09_KNOWLEDGE" / "index.json"


def test_a_shadow_governance_directory_under_06_runtime_cannot_capture_records(tmp_path):
    """The nested path an earlier revision wrote to exists on real installs."""
    (tmp_path / "09_KNOWLEDGE").mkdir()
    (tmp_path / "08_GOVERNANCE").mkdir()
    shadow = tmp_path / "06_RUNTIME" / "ace" / "08_GOVERNANCE"
    shadow.mkdir(parents=True)

    governor = Governor(str(tmp_path / "06_RUNTIME" / "ace"))

    root = tmp_path.resolve()
    assert governor.ace_runtime_dir == root
    assert shadow.resolve() not in governor.knowledge_records_file.parents


def test_duplicate_conclusion_in_canonical_knowledge_is_found(tmp_path):
    conclusion = "碎片索引积压 903 个未考古文件，需要按优先级批量处理考古任务。"
    _seed(tmp_path, conclusion)
    governor = Governor(str(tmp_path))

    similar = governor._search_existing_knowledge({
        "title": conclusion,
        "status": "FACT",
        "confidence": 0.9,
        "evidence": ["e"],
        "references": ["e"],
        "source": "runtime",
    })

    assert similar, "canonical knowledge duplicate was invisible"
    assert similar[0]["similarity"] >= 0.7
    assert similar[0]["id"] == "EXP-SEED-1"


def test_repeated_statement_is_not_admitted_as_new_knowledge(tmp_path):
    conclusion = "碎片索引积压 903 个未考古文件，需要按优先级批量处理考古任务。"
    _seed(tmp_path, conclusion)
    governor = Governor(str(tmp_path))

    record = governor.evaluate({
        "id": "candidate-1",
        "title": conclusion,
        "status": "FACT",
        "confidence": 0.95,
        "evidence": ["a", "b"],
        "references": ["a", "b"],
        "source": "runtime",
    })

    assert record.decision != "pass"
    assert record.criteria.duplication_risk == 0.8