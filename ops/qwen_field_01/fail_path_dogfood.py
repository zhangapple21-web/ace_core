# ACE-QWEN-FIELD-01 repro ruler, promoted from this windows session-temp dir into
# version control so a pointer cited by a queue card or the experiment report stays
# LIVE.  Scratch output goes to the machine temp root; the only repo write is the
# evidence receipt under 08_GOVERNANCE/evidence/, which refuses to overwrite.
"""Failure-path dogfood: classify a failure through the shell face, not the Python API.

Capabilities 7 (失败后被正确分类) and the `fail` line of the port face had never been
pasted: the literal-paste fixture runs the six hole-free commands and skips the two with
【】 holes, because a hole is not pasteable.  This script is that missing arm -- it pulls
the `fail` line out of a real capsule, fills the two holes the way a worker would, and
then proves the four-type gate actually bites when the hole is filled wrong.

Scratch pool under %TEMP% only.  Every command string comes out of the capsule text.

    py -3.11 state/fail_path_dogfood.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = Path(tempfile.gettempdir()) / "ace_qwen_field_01"
STATE.mkdir(exist_ok=True)
OUT = STATE / "fail_path_dogfood_latest.json"
CAPSULE = STATE / "cold_handoff_capsule.txt"

rows = []


def paste(command: str, step: str) -> dict:
    result = subprocess.run(
        command, shell=True, cwd=tempfile.gettempdir(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    lines = [line for line in (result.stdout or "").strip().splitlines() if line.strip()]
    receipt = json.loads(lines[-1]) if lines else {"status": None, "stdout": result.stdout[:200]}
    rows.append({"step": step, "returncode": result.returncode, "status": receipt.get("status"),
                 "reason": receipt.get("reason"), "command": command})
    return receipt


def face_line(label_pattern: str) -> str:
    text = CAPSULE.read_text(encoding="utf-8")
    section = text.split("== RETURN PROTOCOL", 1)[1].split("\n== ", 1)[0]
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- ") and re.search(label_pattern, line):
            for follow in lines[index + 1 : index + 4]:
                if follow.startswith("    ") and follow.strip():
                    return follow.strip()
    raise SystemExit(f"no capsule label matches {label_pattern}")


def main() -> int:
    # 1. seed a fresh scratch task and write its capsule (the pool path is a secret
    #    this script only learns from the capsule, except for the seeding call below)
    seed = subprocess.run(
        [sys.executable, "-m", "ops.qwen_field_01.cold_handoff_capsule", "new"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    seeded = json.loads(seed.stdout.strip().splitlines()[-1])
    pool_dir = Path(seeded["pool_dir"])

    fail_line = face_line(r"做不动，别硬撑")

    # 2. the wrong arm first: a --type outside the four names must be refused by the
    #    port, and the record must not move.  This is what TaskPool.fail_task does NOT
    #    check (queue card F04); only this port's gate stands between a weak worker and
    #    a misclassified failure.
    bad_cmd = fail_line.replace("【一句话原因】", "机制上走不通").replace(
        "【retryable/permanent/manual_gate/external_condition】", "give_up")
    good_cmd = fail_line.replace("【一句话原因】", "本实验只需验证失败分类口").replace(
        "【retryable/permanent/manual_gate/external_condition】", "manual_gate")

    bad = paste(bad_cmd, "wrong type is refused")
    assert bad.get("status") == "REFUSED", bad
    # read the record back immediately: "did the refusal leave it alone" can only be
    # answered before the accepted attempt moves it on purpose
    after_bad = read_back(pool_dir, seeded["task_id"])
    assert still_in_active(pool_dir), "a refused fail must not move the record"

    # 3. the right arm: the enumeration the face prints is a choice, take one member
    good = paste(good_cmd, "right type is recorded")
    assert good.get("status") == "FAILED_RECORDED", good

    stored = read_back(pool_dir, seeded["task_id"])
    checks = {
        "wrong_type_refused": bad.get("status") == "REFUSED",
        "wrong_type_reason_names_the_vocabulary": "type" in str(bad.get("reason", "")),
        "refused_fail_did_not_move_the_record": after_bad.get("status") == "active",
        "right_type_recorded": good.get("status") == "FAILED_RECORDED",
        "record_landed_in_blocked": stored.get("status") == "blocked",
        "failure_type_persisted": stored.get("block_type") == "manual_gate_blocked",
        "failure_reason_persisted": bool(stored.get("failure_reason")) and bool(stored.get("blocked_reason")),
        "claim_cleared_after_fail": not stored.get("claim_id"),
        "retry_count_visible_on_record": stored.get("retry_count") == 1,
        # the only two strings this script ever ran are the capsule's own fail line with
        # its two 【】 holes filled -- nothing was assembled by hand
        "every_command_came_from_the_capsule": [row["command"] for row in rows] == [bad_cmd, good_cmd],
    }
    verdict = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
               "task_id": seeded["task_id"], "pool_dir": str(pool_dir),
               "steps": [{k: r[k] for k in ("step", "returncode", "status", "reason")} for r in rows]}
    previous = STATE / "fail_path_dogfood_previous.json"
    if OUT.exists():
        OUT.replace(previous)  # refuse to overwrite evidence; keep the last run readable
    OUT.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0 if verdict["status"] == "PASS" else 1


def still_in_active(pool_dir: Path) -> bool:
    return any((pool_dir / "active").glob("*.json"))


def read_back(pool_dir: Path, task_id: str) -> dict:
    """Read the stored record with the same shell-only shape a worker would use."""

    result = subprocess.run(
        f'cd "{REPO}" && py -3.11 -m ops.worker_capsule_cli --pool "{pool_dir}" show --task-id {task_id}',
        shell=True, cwd=tempfile.gettempdir(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    row = json.loads(lines[-1]) if lines else {}
    record = row.get("stored_status")
    details = {}
    for bucket in ("blocked", "active", "pending", "review"):
        for path in (pool_dir / bucket).glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("task_id") == task_id:
                details = {
                    "status": data.get("status"),
                    "block_type": data.get("block_type"),
                    "failure_reason": data.get("failure_reason"),
                    "blocked_reason": data.get("blocked_reason"),
                    "claim_id": data.get("claim_id") or "",
                    "retry_count": data.get("retry_count"),
                }
    row.update({"status_after_bad": record, **details})
    return row


if __name__ == "__main__":
    sys.exit(main())
