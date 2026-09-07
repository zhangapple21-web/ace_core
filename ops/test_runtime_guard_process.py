import json
import os
import subprocess
import sys
from pathlib import Path


def test_new_python_entrypoint_inherits_closed_gate(tmp_path: Path):
    state = tmp_path / "continue_gate_runtime_state.json"
    state.write_text(
        json.dumps({"handoff_required": True, "prior_attempt_without_receipt": True, "failure_count": 0, "context_id": "stale"}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CONTINUE_GATE_STATE"] = str(state)
    env.pop("PYTHONPATH", None)
    env.pop("CONTINUE_GATE_BYPASS", None)
    child = subprocess.run(
        [sys.executable, "-c", "import socket; socket.create_connection(('127.0.0.1', 1), timeout=0.1)"],
        cwd=r"C:\tmp\ace_core",
        env=env,
        capture_output=True,
        text=True,
    )
    assert child.returncode != 0
    assert "continue_gate CLOSED_AND_HANDOFF" in (child.stderr + child.stdout)
    assert (tmp_path / "continue_gate_runtime_receipts.jsonl").is_file()


