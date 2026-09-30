import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.memory_index import MemoryIndex, MemoryIndexIntegrityError
from core.self_healing import SelfHealing


class _Identity:
    name = "ACE-test"

    def continuity_mark(self):
        return "test-continuity"


class _Lexicon:
    def classify(self, _text):
        return []


def _index(directory):
    return MemoryIndex(directory, _Identity(), _Lexicon())


def test_corrupt_memory_index_fails_closed_without_rewriting_source(tmp_path):
    index_file = tmp_path / "memory_index.json"
    corrupt = b'{"entries":[\n'
    index_file.write_bytes(corrupt)

    with pytest.raises(MemoryIndexIntegrityError, match="memory_index_unreadable"):
        _index(tmp_path)

    assert index_file.read_bytes() == corrupt


def test_failed_atomic_save_preserves_last_good_file_and_memory(tmp_path, monkeypatch):
    index = _index(tmp_path)
    index.add(title="baseline", content="kept")
    before = index.index_file.read_bytes()
    before_count = index.get_stats()["total"]

    def fail_replace(_source, _destination):
        raise OSError("injected replace failure")

    monkeypatch.setattr("core.memory_index.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        index.add(title="candidate", content="not persisted")

    assert index.index_file.read_bytes() == before
    assert index.get_stats()["total"] == before_count
    assert not list(tmp_path.glob("memory_index.json.*.tmp"))


def test_concurrent_memory_adds_are_atomic_and_recoverable(tmp_path):
    index = _index(tmp_path)

    def add(number):
        return index.add(title=f"entry-{number}", content=f"body-{number}")

    with ThreadPoolExecutor(max_workers=8) as executor:
        ids = list(executor.map(add, range(24)))

    reloaded = _index(tmp_path)
    assert len(set(ids)) == 24
    assert reloaded.get_stats()["total"] == 24
    assert {entry["id"] for entry in reloaded.get_recent(24)} == set(ids)
    assert json.loads(reloaded.index_file.read_text(encoding="utf-8"))["entry_count"] == 24


def test_self_healing_checks_runtime_index_and_never_rebuilds_it_empty(tmp_path):
    runtime_data = tmp_path / "06_RUNTIME" / "ace" / "data" / "memory"
    runtime_data.mkdir(parents=True)
    legacy_data = tmp_path / "02_MEMORY"
    legacy_data.mkdir()
    (legacy_data / "memory_index.json").write_text("broken legacy file", encoding="utf-8")

    active_index = runtime_data / "memory_index.json"
    active_index.write_text(json.dumps({"entries": [{"id": "kept"}]}), encoding="utf-8")
    healing = SelfHealing(runtime_data)
    assert healing._check_memory_integrity(tmp_path)["issues"] == []

    active_index.write_text("broken active file", encoding="utf-8")
    before = active_index.read_bytes()
    issue = healing._check_memory_integrity(tmp_path)["issues"][0]
    assert issue["type"] == "memory_index_corruption"
    assert issue["fixable"] is False
    assert issue["recovery_required"] is True

    healing.diagnose = lambda _base_dir=None: {
        "health_score": 50,
        "issue_count": 1,
        "issues": [issue],
    }
    result = healing.heal(tmp_path)

    assert result["skipped"] == 1
    assert result["fixed"] == 0
    assert active_index.read_bytes() == before
    assert (legacy_data / "memory_index.json").read_text(encoding="utf-8") == "broken legacy file"
