"""Bounded inventory of owned remote Git recovery roots.

This tool intentionally uses only ``git ls-remote`` plus local checkout
metadata.  It does not fetch, stage, commit, push, change GitHub settings, or
interpret repository metadata as ACE Runtime state.  Visibility and branch
protection are explicit inputs because Git transport alone cannot prove them.

The output is evidence for the civilization map, not a Scheduler/TaskPool
command and not a secret scanner.  Secret-shaped paths are reported only as
names by callers; values must never be printed or persisted.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class RemoteRoot:
    full_name: str
    remote_url: str
    branch: str
    remote_head: str
    reachable: bool
    local_path: str
    local_head: str
    dirty_entries: int
    recovery_state: str
    protection_state: str
    visibility_state: str
    error: str = ""


def _run(args: list[str], *, cwd: Optional[Path] = None) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def _remote_head(url: str, branch: str) -> tuple[str, str]:
    code, stdout, stderr = _run(["git", "ls-remote", "--heads", url, branch])
    if code:
        return "", (stderr or stdout).strip()
    for line in stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == f"refs/heads/{branch}":
            return fields[0], ""
    return "", "remote branch missing"


def inventory_remote(
    full_name: str,
    remote_url: str,
    *,
    branch: str = "main",
    local_path: str | Path = "",
    protection_state: str = "UNKNOWN",
    visibility_state: str = "UNKNOWN",
) -> RemoteRoot:
    """Observe one remote and optional checkout without mutating either."""

    remote_head, error = _remote_head(remote_url, branch)
    reachable = bool(remote_head) or error == "remote branch missing"
    root = Path(local_path).resolve() if local_path else None
    local_head = ""
    dirty_entries = 0
    if root and (root / ".git").exists():
        code, stdout, _stderr = _run(["git", "-C", str(root), "rev-parse", "HEAD"])
        if code == 0:
            local_head = stdout.strip()
            _code, status, _status_err = _run(["git", "-C", str(root), "status", "--porcelain=v1"])
            dirty_entries = sum(1 for line in status.splitlines() if line.strip())

    if not reachable:
        state = "REMOTE_UNAVAILABLE"
    elif not remote_head:
        state = "REMOTE_BRANCH_MISSING"
    elif not local_head:
        state = "REMOTE_ONLY"
    elif local_head != remote_head:
        state = "DRIFT"
    elif dirty_entries:
        state = "MATCH_DIRTY"
    else:
        state = "MATCH_CLEAN"
    return RemoteRoot(
        full_name=full_name,
        remote_url=remote_url,
        branch=branch,
        remote_head=remote_head,
        reachable=reachable,
        local_path=str(root or ""),
        local_head=local_head,
        dirty_entries=dirty_entries,
        recovery_state=state,
        protection_state=protection_state,
        visibility_state=visibility_state,
        error=error,
    )


def inventory_many(rows: Iterable[dict]) -> list[RemoteRoot]:
    return [
        inventory_remote(
            row["full_name"],
            row["remote_url"],
            branch=row.get("branch", "main"),
            local_path=row.get("local_path", ""),
            protection_state=row.get("protection_state", "UNKNOWN"),
            visibility_state=row.get("visibility_state", "UNKNOWN"),
        )
        for row in rows
    ]


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="JSON array of remote rows")
    parser.add_argument("--output", help="optional JSON output path")
    args = parser.parse_args(argv)
    rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = [asdict(item) for item in inventory_many(rows)]
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
