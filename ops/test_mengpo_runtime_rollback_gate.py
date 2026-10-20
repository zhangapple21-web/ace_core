"""Isolated red-team checks before any Mengpo daemon wiring.

All candidate writes are confined to pytest temporary roots. Passing tests are
not evidence of readiness or production authority.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.experience_deposition import Experience, ExperienceDeposition
from core.governance import mengpo_runtime
from core.governance.mengpo_runtime import MengpoRuntime
from core.identity import Identity
from core.lexicon import Lexicon
from core.memory_gateway import MemoryGateway
from core.memory_index import MemoryIndex

CANDIDATE = {"id": "c1", "name": "replaceable shape", "category": "fact"}
SUBSTITUTE = {
    "id": "c2",
    "name": "replaceable shape",
    "category": "fact",
    "supersedes": "c1",
}


def _seed_runtime(
    root: Path, *, duplicate_candidate_in_experiences: bool = False
) -> tuple[MengpoRuntime, Path, Path, bytes, bytes]:
    memory_dir = root / "06_RUNTIME" / "ace" / "data" / "memory"
    knowledge_dir = root / "09_KNOWLEDGE"
    memory_dir.mkdir(parents=True, exist_ok=True)
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    lexicon_path = memory_dir / "lexicon.json"
    experiences_path = knowledge_dir / "experiences.json"
    lexicon_path.write_text(
        json.dumps({"concepts": [CANDIDATE, SUBSTITUTE], "sentinel": "keep"}),
        encoding="utf-8",
    )
    experience_items = [
        {"id": "unrelated", "payload": "must-remain"},
    ]
    if duplicate_candidate_in_experiences:
        experience_items.insert(0, dict(CANDIDATE))
    experiences_path.write_text(
        json.dumps({"experiences": experience_items}), encoding="utf-8"
    )
    runtime = MengpoRuntime(root, protected=[])
    return (
        runtime,
        lexicon_path,
        experiences_path,
        lexicon_path.read_bytes(),
        experiences_path.read_bytes(),
    )


def _run(runtime: MengpoRuntime, *, candidate=CANDIDATE, substitute=SUBSTITUTE) -> dict:
    return runtime.run(
        lexicon={"concepts": [candidate, substitute]},
        pollution_scores={str(candidate.get("id") or ""): 0.99},
    )


def _assert_no_partial_commit(runtime, store_before: dict[Path, bytes]):
    assert {path: path.read_bytes() for path in store_before} == store_before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()
    assert not runtime.state_path.exists()
    assert not list(runtime.root.rglob("*.mengpo-backup"))
    assert not list(runtime.root.rglob("*.tmp"))


def _canonical_producer_fixture(root: Path):
    identity = Identity(root, {"identity": {"core_name": "ACE"}})
    lexicon = Lexicon(root / "06_RUNTIME" / "ace" / "data" / "memory", identity)
    index = MemoryIndex(lexicon.data_dir, identity, lexicon)
    gateway = MemoryGateway(index)
    gateway.add(
        title="unrelated rollback sentinel",
        content="the current Mengpo runtime has no approved deletion API here",
        source="isolated-test-fixture",
        category="test",
    )
    deposition = ExperienceDeposition(str(root / "09_KNOWLEDGE"))
    task = SimpleNamespace(
        task_id="RQ-mengpo-producer-fixture",
        guardian_decision="experience",
        hypothesis="one canonical experience",
        tags=["fixture"],
        title="producer schema fixture",
        evidence=[{"source": "test", "content": "fixture evidence"}],
    )
    experience = deposition.deposit_from_task(task)
    assert experience is not None
    return identity, lexicon, index, gateway, deposition, experience


def test_store_write_failure_restores_before_image(tmp_path, monkeypatch):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = (
        _seed_runtime(tmp_path)
    )
    before = {lexicon_path: lexicon_before, experiences_path: experiences_before}
    original_atomic_write = mengpo_runtime._atomic_write_json

    def fail_after_store_write(path, value, **kwargs):
        if path == lexicon_path:
            original_atomic_write(path, value, **kwargs)
            raise OSError("injected store write failure")
        return original_atomic_write(path, value, **kwargs)

    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", fail_after_store_write)
    with pytest.raises(OSError, match="store write"):
        _run(runtime)
    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", original_atomic_write)
    _assert_no_partial_commit(runtime, before)
    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    assert restarted_runtime.run(
        lexicon={"concepts": [CANDIDATE, SUBSTITUTE]},
        pollution_scores={"c1": 0.99},
    )["counts"]["forgotten"] == 1
    assert lexicon_path.read_bytes() != lexicon_before
    assert experiences_path.read_bytes() == experiences_before
    assert not list(runtime.root.rglob("*.tmp"))


def test_receipt_append_failure_restores_all_before_images(tmp_path, monkeypatch):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = (
        _seed_runtime(tmp_path)
    )
    before = {lexicon_path: lexicon_before, experiences_path: experiences_before}

    def fail_receipt_append(path, record):
        if path == runtime.records_path:
            raise OSError("injected receipt append failure")
        return original_append_record(path, record)

    original_append_record = mengpo_runtime._append_jsonl_record
    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", fail_receipt_append)
    with pytest.raises(OSError, match="receipt"):
        _run(runtime)
    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", original_append_record)
    assert {path: path.read_bytes() for path in before} == before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()
    assert not runtime.state_path.exists()
    assert not list(runtime.root.rglob("*.mengpo-backup"))
    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    assert restarted_runtime.run(
        lexicon={"concepts": [CANDIDATE, SUBSTITUTE]},
        pollution_scores={"c1": 0.99},
    )["counts"]["forgotten"] == 1
    assert not list(runtime.root.rglob("*.tmp"))


def test_state_write_failure_restores_all_before_images(tmp_path, monkeypatch):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = (
        _seed_runtime(tmp_path)
    )
    before = {lexicon_path: lexicon_before, experiences_path: experiences_before}
    original_atomic_write = mengpo_runtime._atomic_write_json

    def fail_state_write(path, value, **kwargs):
        if path == runtime.state_path:
            raise OSError("injected runtime state write failure")
        return original_atomic_write(path, value, **kwargs)

    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", fail_state_write)
    with pytest.raises(OSError, match="runtime state"):
        _run(runtime)
    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", original_atomic_write)
    assert {path: path.read_bytes() for path in before} == before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()
    assert not runtime.state_path.exists()
    assert not list(runtime.root.rglob("*.mengpo-backup"))
    assert not list(runtime.root.rglob("*.tmp"))
    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    report = restarted_runtime.run(
        lexicon={"concepts": [CANDIDATE, SUBSTITUTE]},
        pollution_scores={"c1": 0.99},
    )
    assert report["status"] == "APPLIED"


def test_noop_removal_never_reports_applied_or_forgotten(tmp_path):
    runtime, _, _, _, _ = _seed_runtime(tmp_path)
    runtime._forget = lambda artifact, verdict: False
    result = runtime.run(
        lexicon={"concepts": [dict(CANDIDATE), dict(SUBSTITUTE)]},
        pollution_scores={"c1": 0.99},
    )
    assert result.get("status") == "REFUSED"
    assert not result.get("forgotten")
    assert result["counts"]["forgotten"] == 0
    assert result["counts"]["refused"] >= 1
    assert not list(runtime.graveyard_path.glob("*.json"))


def test_new_process_serializes_same_root_transaction_lock(tmp_path):
    lock_child = """
import sys, time
from pathlib import Path
from core.governance.mengpo_runtime import MengpoRuntime
runtime = MengpoRuntime(Path(sys.argv[1]), protected=[])
with runtime._exclusive_lock():
    print("locked", flush=True)
    time.sleep(0.6)
"""
    holder = subprocess.Popen(
        [sys.executable, "-B", "-c", lock_child, str(tmp_path)],
        cwd=Path(__file__).resolve().parent.parent,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "locked"

        contender = [
            sys.executable,
            "-B",
            "-c",
            """
import sys, time
from pathlib import Path
from core.governance.mengpo_runtime import MengpoRuntime
runtime = MengpoRuntime(Path(sys.argv[1]), protected=[])
start = time.monotonic()
with runtime._exclusive_lock():
    elapsed = time.monotonic() - start
print(f"{elapsed:.3f}")
""",
            str(tmp_path),
        ]
        completed = subprocess.run(
            contender,
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        assert float(completed.stdout.strip()) >= 0.40
    finally:
        holder.wait(timeout=5)
        if holder.stdout is not None:
            holder.stdout.close()


def test_new_process_preserves_journal_after_failed_recovery(tmp_path):
    runtime, lexicon_path, _, lexicon_before, _ = _seed_runtime(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import os, sys
from pathlib import Path
from core.governance.mengpo_runtime import MengpoRuntime
from core.governance import mengpo_runtime as module
root = Path(sys.argv[1])
runtime = MengpoRuntime(root, protected=[])
paths = [runtime._store_paths()[0], runtime._store_paths()[1], runtime.records_path,
         runtime.state_path, runtime.graveyard_path / 'c1.json']
runtime._begin_transaction(paths)
runtime._store_paths()[0].write_text('{partial', encoding='utf-8')
def fail_restore(path, data):
    raise OSError('injected recovery failure')
module._atomic_write_bytes = fail_restore
try:
    runtime._recover_transaction()
except OSError:
    os._exit(23)
os._exit(24)
""",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert result.returncode == 23
    assert runtime._transaction_path.exists()
    assert lexicon_path.read_text(encoding="utf-8") == "{partial"

    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    with restarted_runtime._exclusive_lock():
        pass
    assert lexicon_path.read_bytes() == lexicon_before
    assert not runtime._transaction_path.exists()


def test_new_process_recovers_before_images_after_abrupt_exit(tmp_path):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = _seed_runtime(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            (
                """
import os, sys
from pathlib import Path
from core.governance.mengpo_runtime import MengpoRuntime
root = Path(sys.argv[1])
runtime = MengpoRuntime(root, protected=[])
paths = [runtime._store_paths()[0], runtime._store_paths()[1], runtime.records_path,
         runtime.state_path, runtime.graveyard_path / 'c1.json',
         runtime._store_paths()[0].with_suffix('.json.mengpo-backup'),
         runtime._store_paths()[1].with_suffix('.json.mengpo-backup')]
runtime._begin_transaction(paths)
runtime._store_paths()[0].write_text('{partial', encoding='utf-8')
runtime.graveyard_path.joinpath('c1.json').write_text('{partial', encoding='utf-8')
os._exit(23)
"""
            ),
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )
    assert result.returncode == 23

    # The abrupt child exit must leave a durable journal and damaged target files.
    assert runtime._transaction_path.exists()
    assert lexicon_path.read_text(encoding="utf-8") == "{partial"
    assert (runtime.graveyard_path / "c1.json").read_text(encoding="utf-8") == "{partial"

    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    with restarted_runtime._exclusive_lock():
        pass
    assert lexicon_path.read_bytes() == lexicon_before
    assert experiences_path.read_bytes() == experiences_before
    assert not (runtime.graveyard_path / "c1.json").exists()
    assert not runtime.records_path.exists()
    assert not runtime.state_path.exists()
    assert not runtime._transaction_path.exists()
    assert not list(runtime.root.rglob("*.mengpo-backup"))


def test_real_batch_run_recovers_after_partial_second_receipt_write(tmp_path):
    candidates = [
        {"id": f"real-crash-{index}", "name": f"crash shape {index}", "category": "fact"}
        for index in range(2)
    ]
    substitutes = [
        {
            "id": f"real-crash-substitute-{index}",
            "name": f"crash shape {index}",
            "category": "fact",
            "supersedes": f"real-crash-{index}",
        }
        for index in range(2)
    ]
    lexicon_path = tmp_path / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
    lexicon_path.parent.mkdir(parents=True, exist_ok=True)
    lexicon_before = json.dumps(
        {"concepts": candidates + substitutes, "sentinel": "preserve"}
    ).encode()
    lexicon_path.write_bytes(lexicon_before)
    experiences_path = tmp_path / "09_KNOWLEDGE" / "experiences.json"
    experiences_path.parent.mkdir(parents=True, exist_ok=True)
    experiences_before = json.dumps({"experiences": [{"id": "untouched"}]}).encode()
    experiences_path.write_bytes(experiences_before)
    records_path = tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_records.jsonl"
    state_path = tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_runtime_state.json"
    records_before = b'{"action":"historical"}\n'
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_bytes(records_before)
    state_before = json.dumps(
        {"runs": {"2000-01-01": 1}, "last_run_at": None, "last_run_result": {"forgotten": 0, "skipped": 0}}
    ).encode()
    state_path.write_bytes(state_before)
    payload = json.dumps({"concepts": candidates + substitutes})

    child_script = """
import json, os, sys
from pathlib import Path
from core.governance import mengpo_runtime as module
from core.governance.mengpo_runtime import MengpoRuntime
root = Path(sys.argv[1])
original = module._append_jsonl_record
seen = {"count": 0}
def kill_during_second_receipt_write(path, record):
    if path.name == "mengpo_records.jsonl":
        seen["count"] += 1
        if seen["count"] == 2:
            path.parent.mkdir(parents=True, exist_ok=True)
            partial_prefix = '{"partial":'
            assert len(partial_prefix.encode("utf-8")) == 11
            with path.open("a", encoding="utf-8") as handle:
                handle.write(partial_prefix)
                handle.flush()
            os._exit(73)
    return original(path, record)
module._append_jsonl_record = kill_during_second_receipt_write
runtime = MengpoRuntime(root, protected=[])
runtime.run(lexicon=json.loads(sys.argv[2]), pollution_scores={"real-crash-0": 0.99, "real-crash-1": 0.98})
os._exit(74)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", child_script, str(tmp_path), payload],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
        timeout=10,
    )
    assert result.returncode == 73
    transaction_path = tmp_path / "08_GOVERNANCE" / "decisions" / ".mengpo-runtime-transaction.json"
    assert transaction_path.exists()
    assert lexicon_path.read_bytes() != lexicon_before
    crashed_lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    assert {item["id"] for item in crashed_lexicon["concepts"]} == {
        "real-crash-substitute-0",
        "real-crash-substitute-1",
    }
    assert crashed_lexicon["sentinel"] == "preserve"
    # These targets were journaled but had not yet been modified at this failpoint.
    assert experiences_path.read_bytes() == experiences_before
    assert state_path.read_bytes() == state_before
    lexicon_backup = lexicon_path.with_suffix(".json.mengpo-backup")
    experiences_backup = experiences_path.with_suffix(".json.mengpo-backup")
    assert lexicon_backup.exists()
    backup_lexicon = json.loads(lexicon_backup.read_text(encoding="utf-8"))
    assert {item["id"] for item in backup_lexicon["concepts"]} == {
        "real-crash-1",
        "real-crash-substitute-0",
        "real-crash-substitute-1",
    }
    assert not experiences_backup.exists()
    tombstones = list((tmp_path / "08_GOVERNANCE" / "civilization" / "graveyard" / "runtime").glob("*.json"))
    assert {path.stem for path in tombstones} == {"real-crash-0", "real-crash-1"}
    receipt_lines = records_path.read_text(encoding="utf-8").splitlines()
    assert len(receipt_lines) == 3  # historical baseline, first receipt, partial second receipt
    assert json.loads(receipt_lines[0]) == {"action": "historical"}
    first_receipt = json.loads(receipt_lines[1])
    assert first_receipt["artifact_id"] == "real-crash-0"
    assert first_receipt["action"] == "forget"
    assert receipt_lines[2] == '{"partial":'
    tombstone_payloads = [json.loads(path.read_text(encoding="utf-8")) for path in tombstones]
    assert {item["id"] for item in tombstone_payloads} == {"real-crash-0", "real-crash-1"}
    assert all(item["payload"]["id"] == item["id"] for item in tombstone_payloads)

    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    with restarted_runtime._exclusive_lock():
        pass
    assert lexicon_path.read_bytes() == lexicon_before
    assert experiences_path.read_bytes() == experiences_before
    assert records_path.read_bytes() == records_before
    assert state_path.read_bytes() == state_before
    assert not list(restarted_runtime.graveyard_path.glob("*.json"))
    assert not transaction_path.exists()
    assert not list(tmp_path.rglob("*.mengpo-backup"))


def test_real_batch_run_recovers_after_run_state_commit_before_journal_finish(tmp_path):
    candidates = [
        {"id": f"state-crash-{index}", "name": f"state crash {index}", "category": "fact"}
        for index in range(2)
    ]
    substitutes = [
        {
            "id": f"state-crash-substitute-{index}",
            "name": f"state crash {index}",
            "category": "fact",
            "supersedes": f"state-crash-{index}",
        }
        for index in range(2)
    ]
    lexicon_path = tmp_path / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
    lexicon_path.parent.mkdir(parents=True, exist_ok=True)
    lexicon_before = json.dumps(
        {"concepts": candidates + substitutes, "sentinel": "state-recovery"}
    ).encode()
    lexicon_path.write_bytes(lexicon_before)
    experiences_path = tmp_path / "09_KNOWLEDGE" / "experiences.json"
    experiences_path.parent.mkdir(parents=True, exist_ok=True)
    experiences_before = json.dumps({"experiences": [{"id": "untouched-state"}]}).encode()
    experiences_path.write_bytes(experiences_before)
    records_path = tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_records.jsonl"
    state_path = tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_runtime_state.json"
    records_before = b'{"action":"historical-state"}\n'
    records_path.parent.mkdir(parents=True, exist_ok=True)
    records_path.write_bytes(records_before)
    state_before = json.dumps(
        {"runs": {"2000-01-01": 1}, "last_run_at": None, "last_run_result": None}
    ).encode()
    state_path.write_bytes(state_before)
    payload = json.dumps({"concepts": candidates + substitutes})

    child_script = """
import json, os, sys
from pathlib import Path
from core.governance import mengpo_runtime as module
from core.governance.mengpo_runtime import MengpoRuntime
root = Path(sys.argv[1])
def kill_after_run_state_commit(self):
    state = json.loads(self.state_path.read_text(encoding="utf-8"))
    assert state["last_run_result"] == {"forgotten": 2, "skipped": 2}
    assert sum(state["runs"].values()) == 2
    os._exit(75)
module.MengpoRuntime._finish_transaction = kill_after_run_state_commit
runtime = MengpoRuntime(root, protected=[])
runtime.run(lexicon=json.loads(sys.argv[2]), pollution_scores={"state-crash-0": 0.99, "state-crash-1": 0.98})
os._exit(76)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", child_script, str(tmp_path), payload],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
        timeout=10,
    )
    assert result.returncode == 75
    transaction_path = tmp_path / "08_GOVERNANCE" / "decisions" / ".mengpo-runtime-transaction.json"
    assert transaction_path.exists()
    assert lexicon_path.read_bytes() != lexicon_before
    crashed_lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    assert {item["id"] for item in crashed_lexicon["concepts"]} == {
        "state-crash-substitute-0",
        "state-crash-substitute-1",
    }
    assert experiences_path.read_bytes() == experiences_before
    crashed_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert crashed_state["last_run_result"] == {"forgotten": 2, "skipped": 2}
    assert sum(crashed_state["runs"].values()) == 2
    receipts = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    assert receipts[0] == {"action": "historical-state"}
    assert [record["artifact_id"] for record in receipts[1:]] == ["state-crash-0", "state-crash-1"]
    tombstones = list((tmp_path / "08_GOVERNANCE" / "civilization" / "graveyard" / "runtime").glob("*.json"))
    assert {path.stem for path in tombstones} == {"state-crash-0", "state-crash-1"}
    lexicon_backup = lexicon_path.with_suffix(".json.mengpo-backup")
    backup_lexicon = json.loads(lexicon_backup.read_text(encoding="utf-8"))
    assert backup_lexicon["sentinel"] == "state-recovery"
    assert {item["id"] for item in backup_lexicon["concepts"]} == {
        "state-crash-1",
        "state-crash-substitute-0",
        "state-crash-substitute-1",
    }

    recovery_child = """
import os, sys
from pathlib import Path
from core.governance import mengpo_runtime as module
from core.governance.mengpo_runtime import MengpoRuntime
root = Path(sys.argv[1])
original_restore = module._atomic_write_bytes
attempts = {"count": 0}
def interrupt_after_first_restore(path, data):
    original_restore(path, data)
    attempts["count"] += 1
    if attempts["count"] == 2:
        os._exit(77)
module._atomic_write_bytes = interrupt_after_first_restore
runtime = MengpoRuntime(root, protected=[])
with runtime._exclusive_lock():
    pass
os._exit(78)
"""
    interrupted = subprocess.run(
        [sys.executable, "-B", "-c", recovery_child, str(tmp_path)],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
        timeout=10,
    )
    assert interrupted.returncode == 77
    assert transaction_path.exists()
    partial_restore_lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
    assert {item["id"] for item in partial_restore_lexicon["concepts"]} == {
        "state-crash-substitute-0",
        "state-crash-substitute-1",
    }
    assert state_path.read_bytes() == state_before
    assert records_path.read_bytes() == records_before
    partial_tombstones = list(
        (tmp_path / "08_GOVERNANCE" / "civilization" / "graveyard" / "runtime").glob("*.json")
    )
    assert partial_tombstones == []
    assert not list(tmp_path.rglob("*.mengpo-backup"))

    retry_runtime = MengpoRuntime(tmp_path, protected=[])
    with retry_runtime._exclusive_lock():
        pass
    assert lexicon_path.read_bytes() == lexicon_before
    assert experiences_path.read_bytes() == experiences_before
    assert records_path.read_bytes() == records_before
    assert state_path.read_bytes() == state_before
    assert not list(retry_runtime.graveyard_path.glob("*.json"))
    assert not transaction_path.exists()
    assert not list(tmp_path.rglob("*.mengpo-backup"))


def test_retry_repairs_partial_tombstone_before_deletion(tmp_path, monkeypatch):
    runtime, _, _, _, _ = _seed_runtime(tmp_path)
    tombstone_path = runtime.graveyard_path / "c1.json"
    original_atomic_write = mengpo_runtime._atomic_write_json
    injected = {"once": True}

    def write_partial_tombstone(path, value, **kwargs):
        if path == tombstone_path and injected["once"]:
            injected["once"] = False
            partial_write = {"id": "c1", "payload": CANDIDATE}
            original_atomic_write(path, partial_write)
            raise OSError("injected partial tombstone write")
        return original_atomic_write(path, value, **kwargs)

    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", write_partial_tombstone)
    with pytest.raises(OSError, match="partial tombstone"):
        _run(runtime)
    monkeypatch.setattr(mengpo_runtime, "_atomic_write_json", original_atomic_write)

    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    report = _run(restarted_runtime)
    tombstone = json.loads(tombstone_path.read_text(encoding="utf-8"))
    assert tombstone["payload"] == CANDIDATE
    assert not runtime._transaction_path.exists()
    assert report["counts"]["forgotten"] == 1
    assert report["forgotten"][0]["applied"] is True


def test_batch_second_receipt_failure_restores_every_candidate(tmp_path, monkeypatch):
    candidates = [
        {"id": f"c{index}", "name": "batch shape", "category": "fact"}
        for index in range(2)
    ]
    substitute = {
        "id": "batch-sub",
        "name": "batch shape",
        "category": "fact",
        "supersedes": "c0",
    }
    lexicon_path = tmp_path / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
    lexicon_path.parent.mkdir(parents=True, exist_ok=True)
    lexicon_path.write_bytes(json.dumps({"concepts": candidates + [substitute]}).encode())
    experiences_path = tmp_path / "09_KNOWLEDGE" / "experiences.json"
    experiences_path.parent.mkdir(parents=True, exist_ok=True)
    experiences_path.write_bytes(json.dumps({"experiences": []}).encode())
    runtime = MengpoRuntime(tmp_path, protected=[])
    before = {lexicon_path: lexicon_path.read_bytes(), experiences_path: experiences_path.read_bytes()}
    original_append = mengpo_runtime._append_jsonl_record
    calls = {"count": 0}

    def fail_second_receipt(path, record):
        if path == runtime.records_path:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("injected second receipt failure")
        return original_append(path, record)

    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", fail_second_receipt)
    with pytest.raises(OSError, match="second receipt"):
        runtime.run(
            lexicon={"concepts": candidates + [substitute]},
            pollution_scores={"c0": 0.99, "c1": 0.98},
        )
    assert calls["count"] == 2
    assert {path: path.read_bytes() for path in before} == before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()
    assert not runtime._transaction_path.exists()

    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", original_append)
    report = runtime.run(
        lexicon={"concepts": candidates + [substitute]},
        pollution_scores={"c0": 0.99, "c1": 0.98},
    )
    assert report["counts"]["forgotten"] == 2
    state = json.loads(runtime.state_path.read_text(encoding="utf-8"))
    assert sum(state["runs"].values()) == 1
    assert state["last_run_result"] == {"forgotten": 2, "skipped": 1}
    assert len(runtime.records_path.read_text(encoding="utf-8").splitlines()) == 2


def test_retry_repairs_partial_receipt_append(tmp_path, monkeypatch):
    runtime, lexicon_path, experiences_path, _, _ = _seed_runtime(tmp_path)
    before_images = {
        lexicon_path: lexicon_path.read_bytes(),
        experiences_path: experiences_path.read_bytes(),
    }
    original_append_record = mengpo_runtime._append_jsonl_record
    injected = {"once": True}

    def partial_receipt_append(path, record):
        if path == runtime.records_path and injected["once"]:
            injected["once"] = False
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record)[:16], encoding="utf-8")
            raise OSError("injected partial receipt append")
        return original_append_record(path, record)

    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", partial_receipt_append)
    with pytest.raises(OSError, match="partial receipt"):
        _run(runtime)
    monkeypatch.setattr(mengpo_runtime, "_append_jsonl_record", original_append_record)

    restarted_runtime = MengpoRuntime(tmp_path, protected=[])
    report = _run(restarted_runtime)
    lines = runtime.records_path.read_text(encoding="utf-8").splitlines()
    parsed = [json.loads(line) for line in lines]
    assert {path: path.read_bytes() for path in before_images} != before_images
    assert report["counts"]["forgotten"] == 1
    assert parsed and all(record["action"] == "forget" for record in parsed)


def test_canonical_lexicon_shape_is_a_name_keyed_dictionary(tmp_path):
    _, lexicon, _, _, _, _ = _canonical_producer_fixture(tmp_path)
    payload = json.loads(lexicon.lexicon_file.read_text(encoding="utf-8"))
    assert isinstance(payload["concepts"], dict)
    assert all(isinstance(value, dict) for value in payload["concepts"].values())


def test_canonical_experience_is_per_record_and_indexed(tmp_path):
    _, _, _, _, deposition, experience = _canonical_producer_fixture(tmp_path)
    record_path = (
        tmp_path / "09_KNOWLEDGE" / "pattern" / f"{experience.experience_id}.json"
    )
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    index = json.loads(deposition.index_path.read_text(encoding="utf-8"))
    assert payload["experience_id"] == experience.experience_id
    assert payload["experience_type"] == "pattern"
    assert index[experience.experience_id]["path"] == str(record_path)
    assert not (tmp_path / "09_KNOWLEDGE" / "experiences.json").exists()


def test_production_dict_lexicon_shape_fails_closed_without_mutating_stores(tmp_path):
    _, lexicon, _, _, _, _ = _canonical_producer_fixture(tmp_path)
    payload = json.loads(lexicon.lexicon_file.read_text(encoding="utf-8"))
    payload["concepts"] = {
        "replaceable shape": {"id": "c1", "name": "replaceable shape", "category": "fact"},
        "replacement concept": {
            "id": "c2",
            "name": "replaceable shape",
            "category": "fact",
            "supersedes": "c1",
        },
    }
    lexicon.lexicon_file.write_text(json.dumps(payload), encoding="utf-8")

    before = lexicon.lexicon_file.read_bytes()
    runtime = MengpoRuntime(tmp_path, protected=[])
    result = runtime.run(
        lexicon=payload,
        pollution_scores={"c1": 0.99},
    )
    assert result.get("status") in {
        "INVALID", "INVALID_STORE", "UNSUPPORTED_INPUT", "REFUSED"
    }
    assert result["counts"]["forgotten"] == 0
    assert lexicon.lexicon_file.read_bytes() == before
    assert not list(runtime.graveyard_path.glob("*.json"))


def test_corrupt_run_state_fails_closed_without_forgetting(tmp_path):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = (
        _seed_runtime(tmp_path)
    )
    before = {lexicon_path: lexicon_before, experiences_path: experiences_before}
    runtime.state_path.write_text("{broken-json", encoding="utf-8")
    result = _run(runtime)
    assert result.get("status") in {"INVALID", "STATE_CORRUPT", "REFUSED"}
    assert {path: path.read_bytes() for path in before} == before
    assert not list(runtime.graveyard_path.glob("*.json"))


def test_wrong_shaped_run_state_fails_closed(tmp_path):
    runtime, lexicon_path, experiences_path, lexicon_before, experiences_before = (
        _seed_runtime(tmp_path)
    )
    before = {lexicon_path: lexicon_before, experiences_path: experiences_before}
    runtime.state_path.write_text(json.dumps(["not", "a", "state"]), encoding="utf-8")
    result = _run(runtime)
    assert result.get("status") in {"INVALID", "STATE_CORRUPT", "REFUSED"}
    assert {path: path.read_bytes() for path in before} == before
    assert not list(runtime.graveyard_path.glob("*.json"))


@pytest.mark.parametrize("experience_type", ["axiom", "constraint"])
def test_long_term_experience_types_are_never_forgettable(experience_type):
    artifact = Experience(
        experience_id="EXP-core-1",
        source_task_id="RQ-core-1",
        experience_type=experience_type,
        conclusion="governed long-term rule",
        evidence=[],
        constraints_updated=[],
        related_concepts=[],
        epistemic_status=("VERIFIED_FACT" if experience_type == "axiom" else "RULE"),
    ).to_dict()
    artifact["name"] = artifact["conclusion"]
    substitute = {
        "id": "replacement",
        "name": "governed long-term rule",
        "superseded_by": "replacement",
    }
    verdict = mengpo_runtime.assess(
        artifact,
        pollution_score=0.99,
        lexicon={"concepts": [substitute]},
        protected=[],
    )
    assert verdict.forgettable is False


def test_experience_deposition_record_is_not_silently_reported_forgotten(tmp_path):
    _, lexicon, _, _, deposition, experience = _canonical_producer_fixture(tmp_path)
    record_path = (
        tmp_path / "09_KNOWLEDGE" / "pattern" / f"{experience.experience_id}.json"
    )
    record_before = record_path.read_bytes()
    index_before = deposition.index_path.read_bytes()
    artifact = experience.to_dict()
    artifact["name"] = experience.conclusion
    substitute = {
        "id": "replacement",
        "name": experience.conclusion,
        "supersedes": experience.experience_id,
    }
    lexicon.lexicon_file.write_text(
        json.dumps({"concepts": [substitute]}, ensure_ascii=False), encoding="utf-8"
    )
    compatibility_store = tmp_path / "09_KNOWLEDGE" / "experiences.json"
    compatibility_store.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    compatibility_before = compatibility_store.read_bytes()
    runtime = MengpoRuntime(tmp_path, protected=[])
    result = runtime.run(
        lexicon={"concepts": [substitute]},
        experiences=[artifact],
        pollution_scores={experience.experience_id: 0.99},
    )
    assert result["counts"]["forgotten"] == 0
    assert not result["forgotten"]
    assert result["status"] == "UNSUPPORTED_INPUT"
    assert "approved store" in result["reason"]
    assert compatibility_store.read_bytes() == compatibility_before
    assert record_path.exists()
    assert record_path.read_bytes() == record_before
    assert deposition.index_path.read_bytes() == index_before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()


@pytest.mark.parametrize("store_state", ["missing", "malformed"])
def test_unavailable_lexicon_fails_closed_before_mutating_anything(tmp_path, store_state):
    runtime, lexicon_path, experiences_path, _, _ = _seed_runtime(tmp_path)
    if store_state == "malformed":
        lexicon_path.write_text("{broken-json", encoding="utf-8")
        experiences_path.write_text(
            json.dumps({"experiences": [{"id": "exp-1", "payload": "should be preserved"}]}),
            encoding="utf-8",
        )
    else:
        lexicon_path.unlink()
    before = {
        path: path.read_bytes()
        for path in (experiences_path,)
    }
    result = _run(runtime)
    assert result.get("status") == "INVALID_STORE"
    assert experiences_path.read_bytes() == before[experiences_path]
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()


@pytest.mark.parametrize("store_state", ["missing", "malformed", "wrong-shape"])
def test_experience_store_availability_fails_closed_before_mutating_lexicon(
    tmp_path, store_state
):
    runtime, lexicon_path, experiences_path, _, _ = _seed_runtime(tmp_path)
    before = lexicon_path.read_bytes()
    if store_state == "missing":
        experiences_path.unlink()
        result = _run(runtime)
        assert result.get("status") == "APPLIED"
        assert result["counts"]["forgotten"] == 1
        assert lexicon_path.read_bytes() != before
        assert list(runtime.graveyard_path.glob("c1.json"))
        assert runtime.records_path.exists()
        return
    elif store_state == "malformed":
        experiences_path.write_text("{broken-json", encoding="utf-8")
    else:
        experiences_path.write_text(json.dumps({"experiences": None}), encoding="utf-8")
    before = lexicon_path.read_bytes()
    result = _run(runtime)
    assert result.get("status") == "INVALID_STORE"
    assert lexicon_path.read_bytes() == before
    assert not list(runtime.graveyard_path.glob("*.json"))
    assert not runtime.records_path.exists()


def test_backup_matches_latest_pre_forget_store_bytes(tmp_path):
    runtime, lexicon_path, experiences_path, _, _ = _seed_runtime(tmp_path)
    experiences_path.unlink()
    experiences_path.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    report = _run(runtime)
    assert report["forgotten"][0]["applied"] is True
    backup = lexicon_path.with_suffix(".json.mengpo-backup")
    assert json.loads(backup.read_text(encoding="utf-8")) == {
        "concepts": [CANDIDATE, SUBSTITUTE],
        "sentinel": "keep",
    }
    new_candidate = {"id": "c3", "name": "second replaceable shape", "category": "fact"}
    new_substitute = {
        "id": "c4",
        "name": "second replaceable shape",
        "category": "fact",
        "supersedes": "c3",
    }
    lexicon_path.write_text(
        json.dumps({"concepts": [new_candidate, new_substitute], "sentinel": "latest"}),
        encoding="utf-8",
    )
    runtime.state_path.unlink()
    report = _run(runtime, candidate=new_candidate, substitute=new_substitute)
    assert report["forgotten"][0]["applied"] is True
    latest_before = {
        "concepts": [new_candidate, new_substitute],
        "sentinel": "latest",
    }
    assert json.loads(backup.read_text(encoding="utf-8")) == latest_before


def test_memory_gateway_index_is_not_a_runtime_deletion_target(tmp_path):
    _, lexicon, _, gateway, _, _ = _canonical_producer_fixture(tmp_path)
    sentinel = gateway.search(keyword="unrelated rollback sentinel")
    assert sentinel
    index_path = gateway.index_file
    before_index = index_path.read_bytes()
    before_lexicon = lexicon.lexicon_file.read_bytes()
    compatibility_store = tmp_path / "09_KNOWLEDGE" / "experiences.json"
    compatibility_store.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    runtime = MengpoRuntime(tmp_path, protected=[])
    result = runtime.run(
        lexicon=json.loads(lexicon.lexicon_file.read_text(encoding="utf-8")),
        pollution_scores={"c1": 0.99},
    )
    assert result["status"] == "UNSUPPORTED_INPUT"
    assert result["counts"]["forgotten"] == 0
    assert gateway.search(keyword="unrelated rollback sentinel")
    assert index_path.read_bytes() == before_index
    assert lexicon.lexicon_file.read_bytes() == before_lexicon


def test_no_op_runtime_run_is_not_confused_with_forgetting(tmp_path):
    runtime, _, _, _, _ = _seed_runtime(tmp_path)
    result = runtime.run(
        lexicon={"concepts": [dict(CANDIDATE), dict(SUBSTITUTE)]},
        pollution_scores={},
    )
    assert result["counts"]["forgotten"] == 0
    assert not result["forgotten"]


def test_two_independent_runtime_instances_cannot_delete_same_candidate(tmp_path):
    candidate = dict(CANDIDATE)
    substitute = dict(SUBSTITUTE)
    root = tmp_path / "concurrent"
    runtime_a, _, _, _, _ = _seed_runtime(root)
    runtime_b = MengpoRuntime(root, protected=[])
    original_locks = [runtime_a._exclusive_lock, runtime_b._exclusive_lock]
    original_run_locked = [runtime_a._run_locked, runtime_b._run_locked]
    attempt_events = [threading.Event(), threading.Event()]
    both_attempted = threading.Event()
    counter_lock = threading.Lock()
    active = 0
    max_active = 0
    results = []

    def tracked_lock(index):
        from contextlib import contextmanager

        @contextmanager
        def acquire():
            attempt_events[index].set()
            if all(event.is_set() for event in attempt_events):
                both_attempted.set()
            with original_locks[index]():
                yield
        return acquire

    def tracked_run(index):
        def execute(**kwargs):
            nonlocal active, max_active
            with counter_lock:
                active += 1
                max_active = max(max_active, active)
            try:
                if not both_attempted.wait(timeout=5):
                    raise AssertionError("both isolated runtimes did not attempt the lock")
                return original_run_locked[index](**kwargs)
            finally:
                with counter_lock:
                    active -= 1
        return execute

    runtime_a._exclusive_lock = tracked_lock(0)
    runtime_b._exclusive_lock = tracked_lock(1)
    runtime_a._run_locked = tracked_run(0)
    runtime_b._run_locked = tracked_run(1)
    ready = threading.Barrier(3)

    def run(runtime):
        ready.wait()
        results.append(runtime.run(
            lexicon={"concepts": [candidate, substitute]},
            pollution_scores={"c1": 0.99},
        ))

    threads = [
        threading.Thread(target=run, args=(runtime,))
        for runtime in (runtime_a, runtime_b)
    ]
    for thread in threads:
        thread.start()
    ready.wait()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive(), "isolated race-test thread did not finish"

    forgotten = [
        entry
        for result in results
        for entry in result.get("forgotten", [])
        if entry["artifact_id"] == "c1"
    ]
    assert max_active == 1
    assert len(forgotten) == 1
    assert all(entry.get("applied") for entry in forgotten)
    assert len(runtime_a.records_path.read_text(encoding="utf-8").splitlines()) == 1
