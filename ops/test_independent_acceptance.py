import json
import subprocess
import sys

from ops.independent_acceptance import build_acceptance_receipt, inspect_task_file
from core.ace_start import ace_start
from core.execution_discipline import protocol_receipt
from ops.test_support import FixtureTaskPool as TaskPool


def test_independent_acceptance_reads_without_repairing(tmp_path):
    path = tmp_path / "task.json"
    payload = {
        "task_id": "RQ-1",
        "status": "active",
        "lease_owner": "window-a",
        "claim_id": "claim-1",
        "fencing_token": 1,
        "outputs": {
            "execution_discipline": {
                "protocol": "ACE-EXECUTION-DISCIPLINE-1.1",
                "start_protocol": "ACE-START-PROTOCOL-2.0",
                "complexity": "simple",
                "pipeline": {},
                "events": [],
            }
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    before = inspect_task_file(path)
    after = inspect_task_file(path)
    receipt = build_acceptance_receipt(
        task_path=path,
        before=before,
        after=after,
        protocol_receipt={
            "valid": True,
            "task_id": "RQ-1",
            "protocol": "ACE-EXECUTION-DISCIPLINE-1.1",
            "start_protocol": "ACE-START-PROTOCOL-2.0",
        },
    )
    assert receipt["verdict"] == "PASS"
    assert receipt["runtime_mutation_by_checker"] is False
    assert receipt["before"]["sha256"] == receipt["after"]["sha256"]


def test_independent_acceptance_rejects_missing_fencing(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(json.dumps({"task_id": "RQ-1", "status": "active"}), encoding="utf-8")
    facts = inspect_task_file(path)
    receipt = build_acceptance_receipt(
        task_path=path,
        before=facts,
        after=facts,
        protocol_receipt={
            "valid": True,
            "task_id": "RQ-1",
            "protocol": None,
            "start_protocol": None,
        },
    )
    assert receipt["verdict"] == "FAIL"
    assert "missing_owner_claim_or_fencing" in receipt["errors"]


def test_independent_acceptance_rejects_forged_or_unbound_protocol_receipt(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(
        json.dumps(
            {
                "task_id": "RQ-1",
                "status": "active",
                "lease_owner": "window-a",
                "claim_id": "claim-1",
                "fencing_token": 1,
            }
        ),
        encoding="utf-8",
    )
    facts = inspect_task_file(path)
    forged = build_acceptance_receipt(
        task_path=path,
        before=facts,
        after=facts,
        protocol_receipt={
            "valid": True,
            "task_id": "RQ-other",
            "protocol": None,
            "start_protocol": None,
        },
    )
    assert forged["verdict"] == "FAIL"
    assert "protocol_receipt_task_mismatch" in forged["errors"]
    assert "missing_execution_discipline_envelope" in forged["errors"]


def test_independent_acceptance_rejects_placeholder_envelope_with_valid_receipt(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(
        json.dumps(
            {
                "task_id": "RQ-1",
                "status": "active",
                "lease_owner": "window-a",
                "claim_id": "claim-1",
                "fencing_token": 1,
                "outputs": {"execution_discipline": {}},
            }
        ),
        encoding="utf-8",
    )
    facts = inspect_task_file(path)
    receipt = build_acceptance_receipt(
        task_path=path,
        before=facts,
        after=facts,
        protocol_receipt={
            "valid": True,
            "task_id": "RQ-1",
            "protocol": "ACE-EXECUTION-DISCIPLINE-1.1",
            "start_protocol": "ACE-START-PROTOCOL-2.0",
        },
    )
    assert receipt["verdict"] == "FAIL"
    assert "invalid_execution_discipline_envelope" in receipt["errors"]


def test_independent_acceptance_replays_real_start_in_separate_process(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task("cross-process acceptance", creator="test")
    task_path = tmp_path / "task_pool" / "pending" / f"{task.task_id}.json"
    before = inspect_task_file(task_path)
    assert ace_start(pool, task.task_id, "window-a", lease_seconds=60)["status"] == "STARTED"
    task_path = tmp_path / "task_pool" / "active" / f"{task.task_id}.json"
    protocol_path = tmp_path / "protocol.json"
    before_path = tmp_path / "before.json"
    protocol_path.write_text(json.dumps(protocol_receipt(pool.load_task(task.task_id))), encoding="utf-8")
    before_path.write_text(json.dumps(before), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "ops.independent_acceptance",
            "--task",
            str(task_path),
            "--before",
            str(before_path),
            "--protocol",
            str(protocol_path),
        ],
        cwd=str(tmp_path),
        env={**__import__("os").environ, "PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parents[1])},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    receipt = json.loads(proc.stdout)
    assert receipt["verdict"] == "PASS"
    assert receipt["runtime_mutation_by_checker"] is False



