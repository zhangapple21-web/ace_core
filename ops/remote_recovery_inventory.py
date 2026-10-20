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
import ctypes
import importlib.metadata
import shutil
import sys
import time
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
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
        return "", f"git ls-remote failed (exit {code}); diagnostic suppressed"
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
        remote_url=safe_remote_url(remote_url),
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


def safe_remote_url(url: str) -> str:
    """Only transport endpoints without credentials or query data are evidence."""
    try:
        if "://" not in url:
            return "REDACTED_NON_URL_REMOTE"
        parts = urlsplit(url)
        if parts.username or parts.password or parts.query or parts.fragment:
            return "REDACTED_CREDENTIAL_BEARING_REMOTE"
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except ValueError:
        return "REDACTED_INVALID_REMOTE"


def _observe(args: list[str]) -> dict:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode:
            return {"status": "UNKNOWN", "reason": "command_failed", "returncode": result.returncode}
        return {"status": "OBSERVED", "output": result.stdout}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "UNKNOWN", "reason": "command_unavailable_or_timeout"}


def windows_metadata() -> dict:
    if os.name != "nt":
        return {"status": "UNKNOWN", "reason": "not_windows"}
    # No action arguments, registry values, process command lines or task XML.
    script = r'''$ErrorActionPreference='Stop'; $r=@{};
try { $r.tasks=@(Get-ScheduledTask | ForEach-Object { [pscustomobject]@{name=$_.TaskName;path=$_.TaskPath;state=[string]$_.State;action_count=@($_.Actions).Count;trigger_count=@($_.Triggers).Count} }) } catch {$r.tasks_status='UNKNOWN'};
$r.startup_keys=@(); foreach($p in @('HKCU:\Software\Microsoft\Windows\CurrentVersion\Run','HKLM:\Software\Microsoft\Windows\CurrentVersion\Run','HKCU:\Software\Microsoft\Windows\CurrentVersion\RunOnce','HKLM:\Software\Microsoft\Windows\CurrentVersion\RunOnce')) { try { $k=Get-Item -LiteralPath $p -ErrorAction Stop; $r.startup_keys+=@{path=$p;names=@($k.GetValueNames())} } catch {$r.startup_keys+=@{path=$p;status='UNKNOWN'}} };
$r.environment_names=@(); foreach($p in @('HKCU:\Environment','HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment')) {try {$k=Get-Item -LiteralPath $p -ErrorAction Stop;$r.environment_names+=@{scope=$p;names=@($k.GetValueNames())}} catch {$r.environment_names+=@{scope=$p;status='UNKNOWN'}}};
$r.startup_folders=@(); foreach($p in @([Environment]::GetFolderPath('Startup'),[Environment]::GetFolderPath('CommonStartup'))) {if($p) {try {$r.startup_folders+=@{path=$p;names=@(Get-ChildItem -LiteralPath $p -Force -ErrorAction Stop | Select-Object -ExpandProperty Name)}} catch {$r.startup_folders+=@{path=$p;status='UNKNOWN'}}}};
try {$r.listening_ports=@(Get-NetTCPConnection -State Listen | Select-Object LocalPort,OwningProcess -Unique)} catch {$r.ports_status='UNKNOWN'};
$r | ConvertTo-Json -Depth 6 -Compress'''
    observed = _observe(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
    if observed["status"] != "OBSERVED":
        return observed
    try:
        return {"status": "OBSERVED", **json.loads(observed["output"])}
    except ValueError:
        return {"status": "UNKNOWN", "reason": "invalid_metadata_json"}


def drive_metadata() -> list[dict]:
    rows = []
    for drive in ("C:", "D:", "X:", "Y:"):
        target = ""
        if os.name == "nt":
            buffer = ctypes.create_unicode_buffer(32768)
            if ctypes.windll.kernel32.QueryDosDeviceW(drive, buffer, len(buffer)):
                target = buffer.value
        rows.append({"drive": drive, "device_target": target, "status": "OBSERVED" if target else "UNKNOWN"})
    for row in rows:
        row["aliases"] = [other["drive"] for other in rows if other is not row and row["device_target"] and row["device_target"] == other["device_target"]]
        target = row["device_target"]
        row["mapped_parent_drive"] = target[4:6] if target.startswith("\\??\\") and len(target) > 6 and target[5] == ":" else None
        row["independent_backup_medium"] = "NO_SUBDIRECTORY_MAPPING" if row["mapped_parent_drive"] else "UNVERIFIED"
    return rows


DEPENDENCY_NAMES = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock", "poetry.lock", "Pipfile.lock", "pyproject.toml", "requirements.txt", "requirements-dev.txt", "setup.py", "setup.cfg", ".gitmodules"}
PRUNED_NAMES = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "cache", "$recycle.bin", "system volume information"}


def filesystem_metadata(roots: Iterable[str], *, max_entries: int = 200000, max_seconds: float = 45, max_records: int = 5000) -> dict:
    records, repositories, errors = [], [], []
    count = 0
    started = time.monotonic()
    truncated = False
    for root in roots:
        if not Path(root).is_dir():
            errors.append({"root": root, "reason": "root_unavailable"})
            continue
        def onerror(error):
            if len(errors) < 100:
                errors.append({"path": str(error.filename), "reason": "directory_unreadable"})
        for current, dirs, files in os.walk(root, onerror=onerror, followlinks=False):
            count += len(dirs) + len(files)
            if count > max_entries or time.monotonic() - started > max_seconds or len(records) >= max_records:
                truncated = True
                break
            if ".git" in dirs or ".git" in files:
                repositories.append(current)
            dirs[:] = [d for d in dirs if d.lower() not in PRUNED_NAMES and not any(s in d.lower() for s in ("credential", "secret", "cookie")) and not Path(current, d).is_symlink() and not (hasattr(Path(current, d), "is_junction") and Path(current, d).is_junction())]
            for name in files:
                lower = name.lower()
                if lower.startswith(".env") or any(s in lower for s in ("credential", "secret", "cookie", "token", "password")):
                    continue
                category = ""
                if name in DEPENDENCY_NAMES:
                    category = "dependency_manifest_or_lock"
                elif lower.endswith((".db", ".sqlite", ".sqlite3", "-wal", "-shm", ".db-journal", ".sqlite-journal")):
                    category = "database_or_sidecar"
                elif lower.endswith((".log", ".jsonl")):
                    category = "log_or_append_state"
                elif lower.endswith((".exe", ".dll", ".whl")):
                    category = "generated_or_external_binary"
                if category and len(records) < max_records:
                    path = Path(current, name)
                    try:
                        stat = path.stat()
                        records.append({"path": str(path), "category": category, "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns, "validation": "METADATA_ONLY_CONTENT_NOT_READ"})
                    except OSError:
                        if len(errors) < 100:
                            errors.append({"path": str(path), "reason": "stat_failed"})
        if truncated:
            break
    return {"status": "PARTIAL" if truncated or errors else "OBSERVED", "roots": list(roots), "entries_seen": count, "truncated": truncated, "records": records, "repositories": repositories, "errors": errors, "limits": {"entries": max_entries, "seconds": max_seconds, "records": max_records}, "database_consistency": "UNVERIFIED_NO_DB_OPEN_OR_SNAPSHOT"}


def hidden_dependencies(roots: list[str]) -> dict:
    filesystem = filesystem_metadata(roots)
    submodules = []
    for repo in filesystem["repositories"]:
        if Path(repo, ".gitmodules").is_file():
            observation = _observe(["git", "-C", repo, "config", "--file", ".gitmodules", "--name-only", "--get-regexp", r"^submodule\..*\.path$"])
            submodules.append({"repo": repo, "status": observation["status"], "declared_path_count": len(observation.get("output", "").splitlines()), "checkout_and_dependency_order": "UNVERIFIED"})
    npm = _observe([shutil.which("npm.cmd") or "npm.cmd", "ls", "--global", "--depth=0", "--json", "--ignore-scripts"])
    global_node = {"status": npm["status"]}
    if npm["status"] == "OBSERVED":
        try:
            data = json.loads(npm["output"])
            global_node["packages"] = [{"name": name, "version": info.get("version", "UNKNOWN")} for name, info in data.get("dependencies", {}).items()]
        except ValueError:
            global_node = {"status": "UNKNOWN", "reason": "invalid_json"}
    node = _observe([shutil.which("node") or "node", "--version"])
    return {"schema": "ace.hidden_recovery_inventory.v1", "timestamp": datetime.now(timezone.utc).isoformat(), "status": "PARTIAL", "filesystem": filesystem, "drives": drive_metadata(), "windows": windows_metadata(), "environment_names": sorted(os.environ.keys()), "python": {"executable": sys.executable, "version": sys.version, "packages": sorted([{"name": d.metadata.get("Name", "UNKNOWN"), "version": d.version} for d in importlib.metadata.distributions()], key=lambda p: p["name"].lower()), "scope": "CURRENT_INTERPRETER_ONLY_OTHER_ENVIRONMENTS_UNVERIFIED"}, "node": {"executable": shutil.which("node"), "version": node.get("output", "UNKNOWN").strip() if node["status"] == "OBSERVED" else "UNKNOWN", "global_packages": global_node}, "submodules": submodules, "repository_dependency_graph": "UNKNOWN_METADATA_ONLY_NO_IMPORT_OR_SCRIPT_EXECUTION", "restore_order": ["verify_remote_refs_and_checkout", "review_manifests_locks_and_submodules", "generate_isolated_environments_from_locks", "migrate_or_restore_consistent_state_snapshot", "offline_tests", "human_secret_provisioning", "health_validation_before_startup"], "policy": {"copy_venv_node_modules_cache": False, "read_secrets_env_cookies": False, "execute_startup_or_tasks": False, "production_mutation": False}, "blockers": ["SECRET_SINGLE_POINT_NOT_INSPECTED_OR_BACKED_UP", "DATABASE_AND_APPEND_STATE_BACKUP_CONSISTENCY_UNVERIFIED", "LOCK_REPRODUCIBILITY_AND_ARTIFACT_REBUILD_UNVERIFIED", "TASK_ACTIONS_STARTUP_VALUES_AND_ABSOLUTE_PATH_REFERENCES_UNVERIFIED", "FULL_REMOTE_RESTORE_NOT_EXECUTED_BY_INVENTORY"]}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="JSON array of remote rows")
    parser.add_argument("--hidden-root", action="append", help="bounded metadata-only filesystem scan; repeatable")
    parser.add_argument("--output", help="optional JSON output path")
    args = parser.parse_args(argv)
    if bool(args.input) == bool(args.hidden_root):
        parser.error("provide either --input or --hidden-root")
    if args.hidden_root:
        result = hidden_dependencies(args.hidden_root)
    else:
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

