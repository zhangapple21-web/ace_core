"""Read-only audit of Git remotes as a recovery-root boundary.

Git is useful as a portable recovery root only when the inspected checkout is
actually recoverable from its configured remote.  This module deliberately
does not fetch, stage, commit, push, repair, or mutate ACE Runtime state.  It
reports the boundary instead of guessing it:

* ``MATCH_CLEAN`` — local HEAD equals the remote branch and the worktree is
  clean; the checkout is recoverable from that remote branch.
* ``MATCH_DIRTY`` — the committed root matches, but uncommitted local material
  is not represented by the remote root.
* ``DRIFT`` — a reachable remote branch exists but its tip differs from the
  local tip; recovery is incomplete until the divergence is reviewed.
* ``NO_REMOTE`` / ``REMOTE_UNAVAILABLE`` / ``DETACHED`` — no recovery claim.

The report is evidence only.  It must not be consumed as a TaskPool command,
owner/lease decision, scheduler signal, or admission decision.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Optional


class GitAuditError(RuntimeError):
    """Raised when a read-only Git observation cannot be completed."""


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise GitAuditError(detail or f"git command failed: {' '.join(args)}")
    return completed.stdout


def _remote_head(repo: Path, remote: str, branch: str) -> str:
    output = _git(repo, "ls-remote", "--heads", remote, branch)
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == f"refs/heads/{branch}":
            return fields[0]
    return ""


@dataclass(frozen=True)
class RepoAudit:
    repo: str
    remote: str
    remote_url: str
    branch: str
    local_head: str
    remote_head: str
    dirty_entries: int
    state: str
    evidence: str
    error: str = ""


def audit_repo(repo: str | Path, remote: str = "origin", branch: Optional[str] = None) -> RepoAudit:
    """Observe one checkout without changing files, refs, or Runtime state."""

    root = Path(repo).resolve()
    try:
        remote_url = _git(root, "remote", "get-url", remote).strip()
    except GitAuditError as exc:
        return RepoAudit(str(root), remote, "", branch or "", "", "", 0, "NO_REMOTE", "remote lookup failed", str(exc))

    try:
        resolved_branch = (branch or _git(root, "branch", "--show-current").strip())
        if not resolved_branch:
            return RepoAudit(str(root), remote, remote_url, "", "", "", 0, "DETACHED", "no symbolic branch", "")
        local_head = _git(root, "rev-parse", "HEAD").strip()
        dirty_entries = sum(1 for line in _git(root, "status", "--porcelain=v1").splitlines() if line.strip())
        try:
            remote_head = _remote_head(root, remote, resolved_branch)
        except GitAuditError as exc:
            return RepoAudit(
                str(root), remote, remote_url, resolved_branch, local_head, "", dirty_entries,
                "REMOTE_UNAVAILABLE", "remote branch lookup failed", str(exc),
            )
        if not remote_head:
            return RepoAudit(
                str(root), remote, remote_url, resolved_branch, local_head, "", dirty_entries,
                "REMOTE_BRANCH_MISSING", "remote is reachable but branch was not found", "",
            )
        if local_head == remote_head:
            state = "MATCH_CLEAN" if dirty_entries == 0 else "MATCH_DIRTY"
            evidence = "local HEAD equals remote branch tip" + ("; worktree is clean" if dirty_entries == 0 else "; worktree has uncommitted entries")
        else:
            state = "DRIFT"
            evidence = "local HEAD differs from remote branch tip; ancestry was not inferred"
        return RepoAudit(
            str(root), remote, remote_url, resolved_branch, local_head, remote_head,
            dirty_entries, state, evidence, "",
        )
    except GitAuditError as exc:
        return RepoAudit(str(root), remote, remote_url, branch or "", "", "", 0, "LOCAL_UNAVAILABLE", "local Git observation failed", str(exc))


def discover_repositories(scan_root: str | Path) -> List[Path]:
    """Find Git roots below ``scan_root`` without descending into Git internals."""

    root = Path(scan_root).resolve()
    found: List[Path] = []
    for current, dirs, _files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in {".git", "node_modules", ".venv", "venv"}]
        current_path = Path(current)
        if (current_path / ".git").is_dir():
            found.append(current_path)
            dirs[:] = []
    return sorted(found)


def audit_many(repositories: Iterable[str | Path], remote: str = "origin") -> List[RepoAudit]:
    return [audit_repo(repo, remote=remote) for repo in repositories]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", help="checkout to inspect; repeatable")
    parser.add_argument("--scan-root", help="discover checkouts below this directory")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)
    repos = [Path(item) for item in (args.repo or [])]
    if args.scan_root:
        repos.extend(discover_repositories(args.scan_root))
    if not repos:
        raise SystemExit("provide --repo or --scan-root")
    audits = audit_many(dict.fromkeys(repos), remote=args.remote)
    payload = [asdict(item) for item in audits]
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in payload:
            print(f"{item['state']}\t{item['repo']}\t{item['branch']}\t{item['local_head'][:12]}\t{item['remote_head'][:12]}\tdirty={item['dirty_entries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
