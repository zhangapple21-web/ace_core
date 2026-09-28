"""POSIX-shape probe of the capsule face -- the debt C-12 第 10 款 ⑤ puts on this window.

A ruled in F06 that today the face only promises a Windows cmd shape, and that the
POSIX cell must be closed *by running it once*, not by a sentence in a document.  This
is that run: it seeds a scratch task, pulls the eight RETURN PROTOCOL commands out of
the capsule text verbatim, and executes each one through a POSIX-shaped shell
(`bash -c`, MSYS/MinGW64 on this box) instead of `cmd /c`.

What this does and does not prove, stated up front because the difference is the whole
point of the receipt:

* it proves whether the face's *shell grammar* survives a POSIX shell -- `cd "C:\\..."`,
  `&&`, quoting, and whether the interpreter token resolves there;
* it does NOT prove the face runs on a POSIX *operating system*: there is no Linux here,
  and `py.exe` is a Windows launcher that MSYS only inherits through PATH.

Scratch pool under the machine temp root only.

    py -3.11 -m ops.qwen_field_01.posix_face_probe
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.ace_start import ace_start  # noqa: E402
from core.task import TaskPool  # noqa: E402
from core.worker_capsule import render_task_capsule  # noqa: E402

RUNTIME = Path(tempfile.gettempdir()) / "ace_qwen_field_01"
RUNTIME.mkdir(exist_ok=True)
CST = timezone(timedelta(hours=8))
EVID = ROOT / "08_GOVERNANCE" / "evidence" / "posix_face_probe_20260928.json"

BASH = next(
    (p for p in (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe") if Path(p).exists()),
    shutil.which("bash") or "",
)

ADMISSION = {
    "source_type": "evidence",
    "source_ref": f"posix-face-probe-{os.getpid()}",
    "why_now": "C-12 第 10 款 ⑤ puts the POSIX run on the face-owning window",
    "evidence": [{"source": "queue/PROTOCOL.md", "content": "C-12 第 10 款 ⑤：只承诺 Windows 形状，POSIX 由真跑一次关闭"}],
    "expected_result": "per-command verdict under POSIX shell semantics",
    "verification_method": "run each face command through bash -c and read the pool back",
    "risk": "scratch pool only",
    "estimated_scope": "one probe",
}


def face_commands(capsule_text: str):
    section = capsule_text.split("== RETURN PROTOCOL", 1)[1].split("\n== ", 1)[0]
    lines = section.splitlines()
    out = []
    for index, line in enumerate(lines):
        if line.startswith("- "):
            for follow in lines[index + 1 : index + 4]:
                if follow.startswith("    ") and follow.strip():
                    out.append((line[2:].split("（")[0].strip(), follow.strip()))
                    break
    return out


def run(shell_path: str, command: str, kind: str) -> dict:
    row = {"kind": kind, "shell": shell_path, "returncode": None, "json_status": None, "stdout_head": "", "stderr_head": ""}
    if not shell_path:
        row["json_status"] = "NO_SHELL_ON_THIS_BOX"
        return row
    result = subprocess.run(
        [shell_path, "--norc", "--noprofile", "-c", command],
        cwd=str(RUNTIME),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    out = (result.stdout or "").strip()
    rows = [line for line in out.splitlines() if line.strip()]
    status = None
    if rows:
        try:
            status = json.loads(rows[-1]).get("status")
        except json.JSONDecodeError:
            status = f"NOT_JSON({rows[-1][:40]})"
    row.update(
        {
            "returncode": result.returncode,
            "json_status": status,
            "stdout_head": out[:200],
            "stderr_head": (result.stderr or "").strip()[:200],
        }
    )
    return row


def probe_token(shell_path: str, token: str) -> dict:
    result = subprocess.run(
        [shell_path, "--norc", "--noprofile", "-c", f"command -v {token} || true"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return {"token": token, "resolved_to": (result.stdout or "").strip() or "ABSENT"}


def main() -> int:
    pool_dir = RUNTIME / f"posix_probe_pool_{os.getpid()}"
    pool = TaskPool(str(pool_dir))
    task = pool.create_task(
        "POSIX 形状探针：把面孔逐条交给 bash -c 跑",
        hypothesis="面孔的 shell 语法在 POSIX 形状下会断在哪一处",
        creator="F@513447f4",
        complexity="simple",
        tags=["research"],
        admission=dict(ADMISSION),
    )
    started = ace_start(pool, task.task_id, "posix-prober", lease_seconds=600)
    assert started["status"] == "STARTED", started
    capsule = render_task_capsule(
        pool, task.task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    assert capsule["status"] == "CAPSULE_READY", capsule

    commands = face_commands(capsule["capsule_text"])
    holes = [name for name, cmd in commands if "【" in cmd]
    runnable = [(name, cmd) for name, cmd in commands if "【" not in cmd]

    rows = [run(BASH, cmd, name) for name, cmd in runnable]
    tokens = [probe_token(BASH, token) for token in ("py", "python", "python3", "cmd")]

    ran_ok = [row for row in rows if row["json_status"] not in (None, "NO_SHELL_ON_THIS_BOX")]
    verdict = {
        "probe": "ace.qwen_field_01.posix_face_probe.v1",
        "at": datetime.now(CST).isoformat(timespec="seconds"),
        "shell_used": BASH or "ABSENT",
        "shell_is_posix_os": False,
        "honesty_note": (
            "这一跑测的是 POSIX **shell 语法**（bash -c），不是 POSIX 操作系统：本机没有 Linux，"
            "`py.exe` 是 Windows 启动器，MSYS 只是从 PATH 继承到它。C-12 第 10 款 ⑤ 那一格只能由这次跑"
            "**部分**关闭，剩下的一半（真·非 Windows 执行域）本机跑不出来，必须登记为未闭而不是宣布已闭。"
        ),
        "task_id": task.task_id,
        "pool_dir": str(pool_dir),
        "face_command_count": len(commands),
        "commands_needing_holes": holes,
        "commands_run_under_posix_shell": [
            {"label": row["kind"], "returncode": row["returncode"], "json_status": row["json_status"],
             "stderr_head": row["stderr_head"]}
            for row in rows
        ],
        "interpreter_tokens_under_posix_shell": tokens,
        "counts": {
            "ran_and_returned_json": len(ran_ok),
            "ran_but_no_json": len([row for row in rows if row["json_status"] is None]),
            "total_runnable": len(rows),
        },
        "receipt_sha256_of_capsule": hashlib.sha256(capsule["capsule_text"].encode("utf-8")).hexdigest(),
    }
    verdict["verdict"] = (
        "POSIX_SHELL_GRAMMAR_BROKEN"
        if verdict["counts"]["ran_but_no_json"]
        else "POSIX_SHELL_GRAMMAR_SURVIVES_ON_WINDOWS_BASH"
        if ran_ok
        else "NO_COMMAND_RAN"
    )
    if EVID.exists():
        raise SystemExit(f"REFUSE_OVERWRITE {EVID} -- this probe is a receipt, not a draft")
    EVID.write_text(json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
