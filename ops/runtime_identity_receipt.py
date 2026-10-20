#!/usr/bin/env python3
"""What code was on disk while the runtime ran, and which process was it?

The runtime is a single pythonw process whose stdout is discarded. It knows what
it loaded; nobody outside it records what it was. That gap has a cost: on
2026-10-17 a running daemon had to be identified twice by hand - its pid, its
logon type, its session, the fact that the definition and the live command line
agreed - and each time the answer lived only in that conversation.

This writes it down. One JSON receipt, refreshed by the same hourly tick that
already runs as SYSTEM, in a path git ignores so recording identity cannot itself
change the dirty flag it is reporting.

What each part is worth, stated as the three kinds of fact this repository asks
for:

  persisted fact    HEAD, branch, tracked-modified paths, untracked count, and the
                    worktree/HEAD blob hashes of the two lifecycle files. These are
                    facts about the disk, checkable by anyone, later, without this
                    process.
  live observation  the OS view of the process: pid, session, executable, command
                    line, creation time; the registered task's action, working
                    directory and logon type; the lock, heartbeat and daemon_state
                    join keys; the anchor set the daemon says it loaded versus the
                    anchor set a fresh start would load now.
  unproven          everything in `unproven`, written into the receipt itself. The
                    main one: a receipt cannot prove which code the *already
                    running* process imported. It can prove what was on disk while
                    it ran and whether that changed after it started, and it names
                    that limit rather than implying more.

Why not a startup wrapper
-------------------------
A wrapper as the task action would write the receipt from inside the start path,
and it was considered and rejected on two measured grounds. It changes the action
of the production task that was just stabilized (the process tree, `/end`
semantics and `IgnoreNew` bookkeeping all depend on the task instance *being* the
pythonw process), for a marginal gain: the command line, interpreter and working
directory a wrapper would capture are already observable from the OS while the
process runs. The part a wrapper cannot supply at all - whether the disk changed
after the process loaded - is exactly what the anchor join below measures. So the
receipt is written by an outside observer, which is the stronger position anyway:
a process describing itself is a claim, not evidence.

Reuse
-----
The anchor set and its hashing are not reimplemented. `REQUIRED_ANCHORS`,
`_sha256_bytes`, `_sha256_json` and `ContinuityAuditor.current_anchor_snapshot()`
come from `core/continuity_audit.py`, so this receipt agrees with
`ops/run_continuity_audit.py` by construction rather than by care.

Usage:
    py -3 ops/runtime_identity_receipt.py                 # write the receipt
    py -3 ops/runtime_identity_receipt.py --json          # write it and print it
    py -3 ops/runtime_identity_receipt.py --print-only    # print without writing
    py -3 ops/runtime_identity_receipt.py --root <dir>

The hourly tick runs every registered entry as `--root <root> --json` and then
judges the entry's snapshot by age, so `--json` prints without suppressing the
write. That is not a detail: the first version of this file read it as "do not
write", and the measured result was an entry that would run green every hour while
the receipt stayed at whatever a human last wrote by hand. The convention was
already established by the other entries in that registry; this file follows it
instead of asking the tick to special-case one entry.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DEFAULT))

RECEIPT_RELPATH = Path("06_RUNTIME") / "ace" / "data" / "memory" / "runtime_identity_receipt.json"
DAEMON_TASK = "ACE_Daemon_Boot"
# The two files whose behaviour decides whether an external finding ever becomes
# work. They are not in REQUIRED_ANCHORS, and they are the ones this session moved.
LIFECYCLE_FILES = ("core/observation.py", "core/observation_to_task.py")

_OBSERVE = object()


def _run(command: list[str], timeout: int = 5) -> str:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (completed.stdout or "").strip()


def _iso(value: float) -> str:
    return datetime.fromtimestamp(value).isoformat()


def observe_processes() -> list:
    """Ask the OS which pythonw processes are running `ace.py daemon`.

    One CIM query rather than a module import: `ops/health_check.py` has a
    per-pid command-line reader, but this runs inside a SYSTEM-scheduled tick and
    should not acquire the patrol's import graph to answer a question about the
    process table. Returns [] when nothing matches, which is a fact too.
    """
    raw = _run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
        "Select-Object ProcessId,SessionId,CommandLine,ExecutablePath,CreationDate | "
        "ConvertTo-Json -Compress",
    ], timeout=20)
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    found = []
    for entry in parsed if isinstance(parsed, list) else []:
        command_line = str(entry.get("CommandLine") or "")
        if "ace.py" not in command_line or "daemon" not in command_line:
            continue
        creation = entry.get("CreationDate")
        # CIM returns either a datetime string or CIM_DATETIME; both are handled by
        # keeping the raw value next to a best-effort epoch.
        epoch = None
        if isinstance(creation, str) and creation.startswith("/Date("):
            try:
                epoch = int(creation[6:creation.index(")")]) / 1000.0
            except (ValueError, IndexError):
                epoch = None
        found.append({
            "pid": int(entry.get("ProcessId") or 0),
            "session_id": entry.get("SessionId"),
            "executable": entry.get("ExecutablePath"),
            "command_line": command_line,
            "creation_time_raw": creation,
            "creation_time_epoch": epoch,
        })
    return found


def _creation_time_epoch(pid: int):
    """Windows creation time for one pid, for pid-reuse sanity.

    `ace_daemon.py` has the same helper (its own docstring says "for PID-reuse
    detection"), but importing that module pulls a five-thousand-line graph into
    the watch; ten lines of ctypes does not.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:  # noqa: BLE001 - a missing ctypes is not worth a crash
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            creation = wintypes.FILETIME()
            if not kernel32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(wintypes.FILETIME()),
                ctypes.byref(wintypes.FILETIME()), ctypes.byref(wintypes.FILETIME()),
            ):
                return None
            ticks = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return None
    return ticks / 10_000_000 - 11_644_473_600


def observe_task_definition(task_name: str = DAEMON_TASK) -> dict:
    """The registered intent: what the task says should be running, and as whom."""
    xml_text = _run(["schtasks", "/query", "/tn", task_name, "/xml"])
    if not xml_text:
        return {"available": False, "task": task_name}
    try:
        import xml.etree.ElementTree as ElementTree

        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        root = ElementTree.fromstring(xml_text)
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "task": task_name, "error": type(exc).__name__}

    def text(path: str):
        node = root.find(path, ns)
        return node.text if node is not None else None

    return {
        "available": True,
        "task": task_name,
        "command": text("./t:Actions/t:Exec/t:Command"),
        "arguments": text("./t:Actions/t:Exec/t:Arguments"),
        "working_directory": text("./t:Actions/t:Exec/t:WorkingDirectory"),
        "logon_type": text("./t:Principals/t:Principal/t:LogonType"),
        "user_id": text("./t:Principals/t:Principal/t:UserId"),
        "run_level": text("./t:Principals/t:Principal/t:RunLevel"),
    }


def observe_git(root: Path) -> dict:
    head = _run(["git", "-C", str(root), "rev-parse", "HEAD"])
    branch = _run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"])
    porcelain = _run(["git", "-C", str(root), "status", "--porcelain=v1"]).splitlines()
    tracked_modified, untracked = [], []
    for line in porcelain:
        entry = line.strip()
        if not entry:
            continue
        if entry.startswith("??"):
            untracked.append(entry[3:].strip())
        elif entry not in (".gitignore",):
            tracked_modified.append(entry)
    return {
        "head": head or None,
        "branch": branch or None,
        "dirty": bool(porcelain),
        "tracked_modified": tracked_modified,
        "untracked_count": len(untracked),
    }


def observe_file(root: Path, relative: str, *, started_at) -> dict:
    path = root / relative
    facts = {"path": relative, "exists": path.is_file()}
    if not path.is_file():
        return facts
    worktree_blob = _run(["git", "-C", str(root), "hash-object", relative])
    head_blob = _run(["git", "-C", str(root), "rev-parse", f"HEAD:{relative}"])
    mtime = path.stat().st_mtime
    facts.update({
        "worktree_git_blob": worktree_blob or None,
        "head_blob": head_blob or None,
        "worktree_matches_head": bool(worktree_blob and head_blob and worktree_blob == head_blob),
        "mtime": _iso(mtime),
        # "changed after the process started" is a fact about the file; it is NOT
        # a claim about what the running process imported, which is why it is a
        # separate field from the blob comparison.
        "changed_after_process_start": (
            None if started_at is None else bool(mtime > started_at)
        ),
    })
    return facts


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _liveness_join(root: Path) -> dict:
    memory = root / "06_RUNTIME" / "ace" / "data" / "memory"
    lock = _read_json(memory / ".daemon.lock")
    heartbeat = _read_json(memory / "heartbeat.json")
    state = _read_json(memory / "daemon_state.json")
    return {
        "lock_pid": lock.get("pid"),
        "lock_run_id": lock.get("run_id"),
        "lock_token": lock.get("token"),
        "lock_created_at": lock.get("created_at"),
        "heartbeat_pid": heartbeat.get("pid"),
        "heartbeat_run_id": heartbeat.get("run_id"),
        "heartbeat_last_beat": heartbeat.get("last_beat"),
        "heartbeat_status": heartbeat.get("status"),
        "daemon_state_pid": state.get("pid"),
        "daemon_state_run_id": state.get("run_id"),
        "run_started_at": state.get("run_started_at"),
        "loaded_anchor_set_sha256": state.get("loaded_anchor_set_sha256"),
        "loaded_anchor_snapshot_at": state.get("loaded_anchor_snapshot_at"),
    }


def build_receipt(root: Path, *, processes=_OBSERVE, task_definition=_OBSERVE,
                  anchors=_OBSERVE, now: float | None = None) -> dict:
    root = Path(root).resolve()
    observed_at = datetime.now() if now is None else datetime.fromtimestamp(now)
    if processes is _OBSERVE:
        processes = observe_processes()
    if task_definition is _OBSERVE:
        task_definition = observe_task_definition()
    if anchors is _OBSERVE:
        try:
            from core.continuity_audit import ContinuityAuditor

            anchors = ContinuityAuditor(root).current_anchor_snapshot()
        except Exception as exc:  # noqa: BLE001 - a receipt may not fail the tick
            anchors = {"anchor_set_sha256": None, "reason_codes": [type(exc).__name__]}

    processes = list(processes or [])
    live = processes[0] if len(processes) == 1 else None
    started_at = live.get("creation_time_epoch") if live else None
    if live is not None and started_at is None:
        started_at = _creation_time_epoch(int(live.get("pid") or 0))

    join = _liveness_join(root)
    pids = [value for value in (
        live.get("pid") if live else None,
        join.get("lock_pid"), join.get("heartbeat_pid"), join.get("daemon_state_pid"),
    ) if value is not None]
    pids_agree = bool(pids) and len(set(pids)) == 1

    # Agreeing on the full command string would be brittle in a way that hides the
    # point: quoting and the spelling of the interpreter path differ between a task
    # definition and a process table, and neither difference means the task is not
    # what is running. What is checked, and recorded, is whether the task's
    # arguments and the interpreter's file name both appear in the live command
    # line - closing the case this session had to close by hand, where a process
    # could have been started by something other than the task that claims it.
    definition_basis = None
    definition_agrees = None
    if task_definition.get("available") and live:
        expected_arguments = (task_definition.get("arguments") or "").strip()
        expected_executable = (task_definition.get("command") or "").strip()
        live_line = live.get("command_line") or ""
        basename = os.path.basename(expected_executable).lower()
        definition_basis = {
            "expected_arguments": expected_arguments or None,
            "expected_executable": expected_executable or None,
            "arguments_present_in_live_command_line": bool(
                expected_arguments and expected_arguments in live_line),
            "executable_basename_present_in_live_command_line": bool(
                basename and basename in live_line.lower()),
            "live_command_line": live_line or None,
        }
        definition_agrees = bool(
            definition_basis["arguments_present_in_live_command_line"]
            and definition_basis["executable_basename_present_in_live_command_line"]
        )

    anchors_agree = None
    if anchors.get("anchor_set_sha256") and join.get("loaded_anchor_set_sha256"):
        anchors_agree = anchors["anchor_set_sha256"] == join["loaded_anchor_set_sha256"]

    return {
        "schema": "ace.runtime_identity_receipt.v1",
        "written_at": observed_at.isoformat(),
        "written_by": {
            "pid": os.getpid(),
            "identity": _run(["whoami"]) or None,
            "session": os.environ.get("SESSIONNAME") or None,
            "python": sys.executable,
            "script": "ops/runtime_identity_receipt.py",
        },
        "process": {
            "observed": live is not None,
            "instance_count": len(processes),
            "pid": live.get("pid") if live else None,
            "session_id": live.get("session_id") if live else None,
            "executable": live.get("executable") if live else None,
            "command_line": live.get("command_line") if live else None,
            "creation_time": _iso(started_at) if started_at else None,
        },
        "definition": task_definition,
        "definition_matches_live_command_line": definition_agrees,
        "definition_match_basis": definition_basis,
        "code": {
            "git": observe_git(root),
            "lifecycle_files": {
                relative: observe_file(root, relative, started_at=started_at)
                for relative in LIFECYCLE_FILES
            },
        },
        "join": dict(join, pids_agree=pids_agree,
                     current_anchor_set_sha256=anchors.get("anchor_set_sha256"),
                     anchor_reason_codes=anchors.get("reason_codes"),
                     anchors_agree=anchors_agree),
        "unproven": [
            "which modules the already-running process imported at start; this "
            "records what was on disk while it ran and whether that changed after "
            "it started, not what it loaded",
            "that the worktree matched HEAD at process start: the blob comparison "
            "is against HEAD as of writing, so a file that changed and was then "
            "reverted, or a commit made after the process started and since "
            "superseded, is invisible to it. The anchor join is the field that "
            "does compare the process's own load-time identity with the disk",
            "that the process was started by the named task, only that the task's "
            "action and the live command line agree",
            "that the pid's code is running now: a pid observed at this moment and "
            "a pid recorded in the lock could be different processes if either was "
            "reused between the two reads",
            "anything about a runtime that is not running: with no process, this is "
            "a receipt about the disk and the last recorded join keys only",
        ],
    }


def write_receipt(root: Path, receipt: dict) -> Path:
    path = Path(root).resolve() / RECEIPT_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT_DEFAULT))
    parser.add_argument(
        "--json",
        action="store_true",
        # The hourly tick runs every registered entry as `--root <root> --json` and
        # then judges the entry's snapshot by age, so this prints *in addition to*
        # writing. The first version of this file read --json as "do not write", and
        # the measured result was an entry that would exit 0 every hour while its
        # snapshot stayed at the last manual run (3.4 minutes old, unchanged): green,
        # silent, and producing nothing. An entry asked to run cannot decline to
        # produce its artifact.
        help="write the receipt and also print it as JSON (the tick's invocation)",
    )
    parser.add_argument("--print-only", action="store_true",
                        help="print without writing, for reading a receipt")
    args = parser.parse_args(argv)

    receipt = build_receipt(Path(args.root))
    if args.print_only:
        path = Path(args.root).resolve() / RECEIPT_RELPATH
    else:
        path = write_receipt(Path(args.root), receipt)
    if args.json or args.print_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"receipt written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
