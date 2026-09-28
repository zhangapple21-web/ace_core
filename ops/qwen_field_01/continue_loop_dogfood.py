# ACE-QWEN-FIELD-01 repro ruler, promoted from this windows session-temp dir into
# version control so a pointer cited by a queue card or the experiment report stays
# LIVE.  Scratch output goes to the machine temp root; the only repo write is the
# evidence receipt under 08_GOVERNANCE/evidence/, which refuses to overwrite.
"""Capability 11 dogfood: a shell-only weak worker that keeps finding work.

The rule for this run is self-imposed and is the whole point: the worker side
may only execute command strings it read out of an ACE receipt or out of the
capsule text itself.  The single bootstrap command is the only command this
script knows by heart.  If ACE's steering face is complete, the loop runs;  if
any hop still needs the worker to remember a flag shape, it stops here instead
of quietly passing in a test harness.

    cd 本仓根 && PYTHONIOENCODING=utf-8 py -3.11 \
        ops/qwen_field_01/continue_loop_dogfood.py

Scratch pool under %TEMP% only; the production TaskPool is never opened.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from core.task import TaskPool  # noqa: E402
CST = timezone(timedelta(hours=8))

WORKER = "qwen-loop-w1"
POOL = Path(tempfile.mkdtemp(prefix="ace_continue_loop_")) / "pool"
# ``--round <tag>`` keeps an earlier PASS on disk while a re-run after a capsule
# change writes its own file; the canonical name is never overwritten.
_round = sys.argv[sys.argv.index("--round") + 1] if "--round" in sys.argv else ""
EVID = REPO / "08_GOVERNANCE" / "evidence" / (
    f"capsule_continuation_loop_20260928{'_' + _round if _round else ''}.jsonl"
)

ADMISSIONS = [
    ("第一个要接着找活的演练任务", "loop-01"),
    ("第二个要接着找活的演练任务", "loop-02"),
    ("第三个留在池里不该被动过的任务", "loop-03"),
]


def _seed():
    """The dispatch side may use the API; the worker side below may not."""

    pool = TaskPool(str(POOL))
    ids = []
    for title, ref in ADMISSIONS:
        task = pool.create_task(
            title,
            hypothesis="交回之后还要能自己找到下一件",
            creator="loop-dispatcher",
            complexity="simple",
            tags=["research"],
            admission={
                "source_type": "system_observation",
                "source_ref": f"qwen-field-01-{ref}",
                "why_now": "prove the loop continues without a scheduler telling it to",
                "evidence": [{"source": "field-scan", "content": "capsule + CLI exist"}],
                "expected_result": "task moved to review by a shell-only worker",
                "verification_method": "this dogfood receipt",
                "risk": "scratch pool only",
                "estimated_scope": "one round",
            },
        )
        ids.append(task.task_id)
    return ids


rows = []


def run(command, note, source="hand_written"):
    """Execute a command string exactly as ACE handed it over (cmd.exe semantics)."""

    at = datetime.now(CST).strftime("%H:%M:%S")
    result = subprocess.run(
        command,
        shell=True,
        # Started from outside the repo: every pasted command has to carry its
        # own cd, because a real worker will not be standing in the repo root.
        cwd=str(Path(tempfile.gettempdir()).resolve()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    stdout = (result.stdout or "").strip()
    lines = [line for line in stdout.splitlines() if line.strip()]
    payload = None
    if len(lines) == 1:
        try:
            payload = json.loads(lines[0])
        except ValueError:
            payload = None
    rows.append(
        {
            "seq": len(rows) + 1,
            "at": at,
            "note": note,
            "command_source": source,
            "command": command,
            "exit": result.returncode,
            "status": (payload or {}).get("status"),
            "reason": (payload or {}).get("reason"),
            "stderr_tail": "" if result.returncode == 0 else (result.stderr or "")[-400:],
        }
    )
    return payload, result


def capsule_command(capsule_text, label_fragment):
    """The command line that follows a port-face label -- paste it, change the holes."""

    lines = capsule_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- ") and label_fragment in line:
            for follow in lines[index + 1 :]:
                if follow.startswith("    ") and follow.strip():
                    return follow.strip()
    return None


prefix = f'cd "{REPO}" && py -3.11 -m ops.worker_capsule_cli --pool "{POOL}"'
bootstrap = f"{prefix} list-pending"

seeded = _seed()
completed = []
blocked = []

listing, _ = run(bootstrap, "the only command this worker knows by heart", "bootstrap")
if listing is None or listing.get("status") != "LISTED":
    raise SystemExit(f"bootstrap failed: {rows[-1]}")

for round_index in range(2):
    target = listing["pending"][0]["task_id"]

    # LISTED tells the worker the shape of the next command; it only has to put
    # in the two values it just read off the screen.
    start_cmd = listing["next_step"].replace("【从上面挑一个 task_id】", target).replace("【你的 worker 名】", WORKER)
    started, _ = run(start_cmd, f"round {round_index + 1}: claim the head of the queue", "listed.next_step")
    if not started or started.get("status") != "STARTED":
        blocked.append(("start", rows[-1]))
        break

    # The start receipt hands over a fully formed render command -- paste it.
    rendered, _ = run(started["next_step"], f"round {round_index + 1}: read the capsule", "start.next_step")
    if not rendered or rendered.get("status") != "CAPSULE_READY":
        blocked.append(("render", rows[-1]))
        break

    hand_back = capsule_command(rendered["capsule_text"], "做完了，交回")
    if hand_back is None:
        blocked.append(("capsule_has_no_submit_line", None))
        break

    payload_path = Path(tempfile.gettempdir()) / f"loop_payload_{round_index + 1}.json"
    payload_path.write_text(
        json.dumps(
            {
                "summary": f"第 {round_index + 1} 件由 shell-only worker 完成",
                "facts": ["全部命令串取自 ACE 回执与胶囊正文"],
                "evidence": [
                    {
                        "content": f"capsule_hash {rendered['capsule_hash'][:12]}",
                        "source": "state/continue_loop_dogfood.py",
                    }
                ],
                "transition": "review",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    submit_cmd = (
        hand_back.replace("【结果.json 的路径】", str(payload_path))
        .replace("【capsule_hash】", rendered["capsule_hash"])
        .replace("【你的worker名】", WORKER)
    )
    assert "【" not in submit_cmd, submit_cmd
    submitted, _ = run(submit_cmd, f"round {round_index + 1}: hand back, pasting the capsule line", "capsule.port_face")
    if not submitted or submitted.get("status") != "SUBMITTED":
        blocked.append(("submit", rows[-1]))
        break
    completed.append({"task_id": target, "receipt": submitted})

    continuation = submitted.get("continuation") or {}
    if not continuation.get("next_commands"):
        blocked.append(("submit_without_continuation", None))
        break

    # Capability 11 in one line: the hand-back receipt is what tells the worker
    # there is still work, and the first of its commands is pasted verbatim.
    listing, _ = run(continuation["next_commands"][0], f"round {round_index + 1}: look for the next job", "submit.continuation")
    if listing is None or listing.get("status") != "LISTED":
        blocked.append(("continuation_read", rows[-1]))
        break

checks = {
    "loop_completed_two_tasks": len(completed) == 2,
    "only_the_bootstrap_was_hand_written": [row["command_source"] for row in rows] == ["bootstrap"] + [row["command_source"] for row in rows[1:]] and all(row["command_source"] != "hand_written" for row in rows[1:]),
    "every_command_carries_its_own_prefix": all(row["command"].startswith(f'cd "{REPO}" &&') and "--pool " in row["command"] for row in rows),
    "every_command_ran": all(row["exit"] == 0 for row in rows),
    "third_task_untouched": seeded[2] in [row["task_id"] for row in listing.get("pending", [])] if listing else False,
    "no_extra_pending_created": listing.get("count") == 1 if listing else False,
    "no_blocked_hops": not blocked,
}

pool = TaskPool(str(POOL))
landed = []
for item in completed:
    stored = pool.load_task(item["task_id"])
    ledger = ((stored.outputs.get("execution_discipline") or {}).get("evidence_ledger") or {}) if stored else {}
    landed.append(
        {
            "task_id": item["task_id"],
            "status": getattr(stored, "status", None),
            "claim_owner": getattr(stored, "lease_owner", None) if stored else None,
            "evidence_rows": len(getattr(stored, "evidence", []) or []),
            "ledger_result_rows": len(ledger.get("result") or []),
        }
    )
checks["truth_landed_on_pool_records"] = all(
    row["status"] == "review" and row["evidence_rows"] >= 1 and row["ledger_result_rows"] >= 1 for row in landed
)

verdict = "PASS" if all(checks.values()) else "FAIL"
header = {
    "run": "capsule_continuation_loop",
    "task": "ACE-QWEN-FIELD-01 capability 11",
    "at": datetime.now(CST).isoformat(timespec="seconds"),
    "pool_dir": str(POOL),
    "scratch_only": str(POOL).startswith(str(Path(tempfile.gettempdir()))),
    "seeded_task_ids": seeded,
    "bootstrap_command": bootstrap,
}
if EVID.exists():
    # Refuse to overwrite a passing record; a failed attempt is kept as its own
    # file so the next run cannot erase the evidence of what broke.
    last = json.loads(EVID.read_text(encoding="utf-8").strip().splitlines()[-1])
    if last.get("verdict") != "FAIL":
        raise SystemExit(f"REFUSE_OVERWRITE {EVID} verdict={last.get('verdict')}")
    archive = EVID.with_name(f"{EVID.stem}_attempt_of_fail{EVID.suffix}")
    if archive.exists():
        raise SystemExit(f"REFUSE_OVERWRITE {archive}")
    EVID.replace(archive)
    print(f"ARCHIVED_FAIL {archive.name}")
with EVID.open("w", encoding="utf-8") as handle:
    handle.write(json.dumps({"kind": "header", **header}, ensure_ascii=False) + "\n")
    for row in rows:
        handle.write(json.dumps({"kind": "step", **row}, ensure_ascii=False) + "\n")
    handle.write(json.dumps({"kind": "landed", "rows": landed}, ensure_ascii=False) + "\n")
    handle.write(json.dumps({"kind": "blocked", "hops": blocked}, ensure_ascii=False) + "\n")
    handle.write(json.dumps({"kind": "checks", "checks": checks, "verdict": verdict}, ensure_ascii=False) + "\n")

print(json.dumps({"verdict": verdict, "checks": checks, "steps": len(rows), "landed": landed, "evidence": str(EVID)}, ensure_ascii=False, indent=2))
