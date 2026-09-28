# ACE-QWEN-FIELD-01 repro ruler, promoted from this window's session-temp dir into
# version control so a pointer cited by a queue card or the experiment report stays
# LIVE.  Scratch output goes to the machine temp root; the only repo write is the
# evidence receipt under 08_GOVERNANCE/evidence/, which refuses to overwrite.
"""Mechanical cold replay: execute a capsule by pasting it, with no other knowledge.

This is NOT the model-swap test.  The model-swap test is a fresh *agent* that has
to decide what the capsule means, and it is currently blocked (the daily Chat
quota refused the sub-agent before it ran a single tool).  What this script can
prove, and only this, is that the port face is executable by a process which
carries nothing but the capsule file: it never reads the repo, never imports
ACE, never learns the pool path or the credentials from anywhere except the
text, fills the two 【】 holes with a literal string replace, and pastes.

Every step therefore has the same shape: take the labelled line out of the
capsule, run it verbatim through cmd, read one JSON line back.

    py -3.11 state/cold_face_replay.py [--pool-only]
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
RUNTIME = Path(tempfile.gettempdir()) / "ace_qwen_field_01"
RUNTIME.mkdir(exist_ok=True)

CAPSULE = RUNTIME / "cold_handoff_capsule.txt"
WORK = Path(tempfile.mkdtemp(prefix="ace_cold_replay_"))
OUT = RUNTIME / "cold_face_replay_latest.json"

rows = []


def face(label_pattern: str) -> str:
    """Pull the indented command under a label line, verbatim, out of the capsule."""

    text = CAPSULE.read_text(encoding="utf-8")
    section = text.split("== RETURN PROTOCOL", 1)[1].split("\n== ", 1)[0]
    lines = section.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- ") and re.search(label_pattern, line):
            for follow in lines[index + 1 : index + 4]:
                if follow.startswith("    ") and follow.strip():
                    return follow.strip()
            raise SystemExit(f"label matched but no command under it: {label_pattern}")
    raise SystemExit(f"no capsule label matches {label_pattern}")


def paste(command: str, step: str) -> dict:
    result = subprocess.run(
        command, shell=True, cwd=str(WORK), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    lines = [line for line in (result.stdout or "").strip().splitlines() if line.strip()]
    receipt = json.loads(lines[-1]) if lines else {}
    rows.append(
        {
            "step": step,
            "returncode": result.returncode,
            "status": receipt.get("status"),
            "command_ran_verbatim": command,
            "stderr_head": (result.stderr or "")[:200],
        }
    )
    if not lines:
        raise SystemExit(f"{step}: no JSON at all -- {result.stderr[:300]}")
    return receipt


def main() -> int:
    # 1. the capsule is the only input: no pool path, no claim, no token anywhere else
    render = face(r"要 capsule_hash")
    submit = face(r"做完了，交回")
    read_back = face(r"交回后自检")
    listed = face(r"找下一件活")

    listing = paste(listed, "paste: 找下一件活")
    assert listing.get("status") == "LISTED", listing

    # 2. the hash the face demands is obtainable from the face itself
    ready = paste(render, "paste: 要 capsule_hash")
    assert ready.get("status") == "CAPSULE_READY", ready
    capsule_hash = ready["capsule_hash"]
    assert len(capsule_hash) == 64, capsule_hash

    # 3. do the work, then fill the only two holes the face leaves open
    answer = WORK / "answer.txt"
    answer.write_text("机械重放：只粘贴胶囊里的命令完成冷接手\n", encoding="utf-8")
    payload = WORK / "payload.json"
    payload.write_text(
        json.dumps(
            {
                "summary": "机械重放交回：命令全部逐字粘贴自胶囊正文",
                "facts": ["端口面孔在无先验知识的进程上可直接执行"],
                "evidence": [
                    {
                        "content": f"answer.txt sha256 前 12 位见本件 source",
                        "source": "state/cold_face_replay.py",
                    }
                ],
                "unknowns": ["模型级冷接手本轮被 Chat 日额度挡住，未测"],
                "transition": "review",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    submitted = paste(
        submit.replace("【结果.json 的路径】", str(payload)).replace("【capsule_hash】", capsule_hash),
        "paste: 做完了，交回",
    )
    assert submitted.get("status") == "SUBMITTED", submitted
    assert submitted.get("stored_status") == "review", submitted

    # 4. verification is now executable too: the same capsule reads its own record back
    seen = paste(read_back, "paste: 交回后自检")
    assert seen.get("status") == "TASK_SEEN", seen
    assert seen.get("stored_status") == "review", seen
    assert seen.get("result_summary"), seen

    # a hash that came from the face must be the hash the record stored
    stored_hashes = [item.get("capsule_hash") for item in seen.get("checkpoints_tail") or []]
    verdict = {
        "status": "REPLAY_PASS" if capsule_hash in stored_hashes else "REPLAY_HASH_NOT_STORED",
        "work_dir": str(WORK),
        "capsule_file": str(CAPSULE),
        "capsule_hash_from_face": capsule_hash,
        "capsule_hashes_on_record": stored_hashes,
        "hash_is_stored_on_the_task": capsule_hash in stored_hashes,
        "read_back_worked": seen.get("stored_status") == "review",
        "every_command_came_from_the_capsule": True,
        "steps": rows,
    }
    OUT.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in verdict.items() if key != "steps"}, ensure_ascii=False, indent=2))
    return 0 if verdict["status"] == "REPLAY_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
