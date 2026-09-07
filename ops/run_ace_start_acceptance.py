"""Produce one bounded, temporary, cross-process ACE start receipt."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ace_start import ace_start
from core.execution_discipline import protocol_receipt
from ops.test_support import FixtureTaskPool as TaskPool
from ops.independent_acceptance import inspect_task_file


def main(argv=None) -> int:
    output = Path(argv[0]) if argv else ROOT / "research" / "ace_start_independent_acceptance_receipt.json"
    with tempfile.TemporaryDirectory(prefix="ace-start-acceptance-") as tmp:
        root = Path(tmp)
        pool = TaskPool(str(root / "task_pool"))
        task = pool.create_task("temporary start acceptance", creator="test")
        pending = root / "task_pool" / "pending" / f"{task.task_id}.json"
        before = inspect_task_file(pending)
        started = ace_start(pool, task.task_id, "acceptance-window", lease_seconds=60)
        active = root / "task_pool" / "active" / f"{task.task_id}.json"
        before_path = root / "before.json"
        protocol_path = root / "protocol.json"
        before_path.write_text(json.dumps(before), encoding="utf-8")
        protocol_path.write_text(json.dumps(protocol_receipt(pool.load_task(task.task_id))), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "ops.independent_acceptance", "--task", str(active), "--before", str(before_path), "--protocol", str(protocol_path)],
            cwd=str(ROOT),
            env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(proc.stderr or "independent acceptance process failed")
        receipt = json.loads(proc.stdout)
        receipt["start_result"] = started
        receipt["scope"] = "temporary TaskPool only"
        receipt["checkout_wide_claim"] = "NOT_MADE"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt.get("verdict") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

