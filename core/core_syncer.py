"""Hash-manifested synchronizer for the ACE civilization repository.

This is deliberately narrower than the historical ``CoreSyncer``.  A dirty
working tree is normal for ACE: it contains runtime receipts, sandbox material,
operator experiments and generated reports.  None of those becomes a Git
commit merely because a daemon cycle ran.

Only a small, explicit motherplate allowlist may be staged.  Each attempted
sync creates an ignored runtime receipt containing both the admissible-file
manifest and the reason a push did or did not occur.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Tuple


class CoreSyncer:
    """Safely commit and push an explicit content manifest, never directories."""

    EXACT_FILES = frozenset({"AGENTS.md", "README.md", "ace_daemon.py"})
    ALLOWED_SUFFIXES = {
        "core": frozenset({".py"}),
        "ops": frozenset({".py"}),
        "docs": frozenset({".md"}),
        "00_ROOT": frozenset({".md"}),
    }

    def __init__(
        self,
        repo_path: str,
        remote: str = "origin",
        branch: str = "main",
        debounce_minutes: int = 60,
        max_automatic_files: int = 12,
    ) -> None:
        self.repo_path = Path(repo_path).resolve()
        self.remote = remote
        self.branch = branch
        self.debounce_minutes = debounce_minutes
        self.max_automatic_files = max_automatic_files
        self._state_file = (
            self.repo_path
            / "06_RUNTIME"
            / "ace"
            / "data"
            / "curator"
            / "civilization_sync_state.json"
        )
        self._latest_file = self._state_file.with_name("civilization_sync_latest.json")
        self._last_push: Optional[str] = None
        self._load_state()

    def _load_state(self) -> None:
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            self._last_push = data.get("last_push")
        except (OSError, ValueError, TypeError):
            self._last_push = None

    def _write_receipt(self, result: Dict[str, Any]) -> None:
        """Persist only diagnostic metadata outside the synchronised allowlist."""
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            state = {
                "last_push": self._last_push,
                "last_commit": result.get("commit_hash"),
                "last_manifest_sha256": result.get("manifest_sha256"),
                "last_status": result.get("status"),
                "updated_at": datetime.now().isoformat(),
            }
            self._state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            self._latest_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            # Receipt failure must not turn an already-completed commit into a
            # reported failure. The caller still gets its concrete Git result.
            pass

    def _run_git(self, *args: str) -> str:
        return self._run_git_raw(*args).strip()

    def _run_git_raw(self, *args: str) -> str:
        """Run Git without altering porcelain output (leading spaces matter)."""
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        completed = subprocess.run(
            ["git", *args], cwd=self.repo_path, capture_output=True, text=True, env=env
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or "git command failed")
        return completed.stdout

    def _remote_head(self) -> Optional[str]:
        output = self._run_git("ls-remote", "--heads", self.remote, self.branch)
        for line in output.splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[1] == f"refs/heads/{self.branch}":
                return fields[0]
        return None

    def _parse_status(self) -> List[Tuple[str, str]]:
        raw = self._run_git_raw("status", "--porcelain=v1", "-z")
        records: List[Tuple[str, str]] = []
        parts = raw.split("\0")
        index = 0
        while index < len(parts):
            entry = parts[index]
            index += 1
            if not entry:
                continue
            if len(entry) < 4:
                raise RuntimeError("UNPARSEABLE_GIT_STATUS")
            xy, path = entry[:2], entry[3:]
            # Rename/copy porcelain entries carry the previous path as the
            # next NUL-delimited item.  The current path is enough for our
            # manifest, but consume the old name to keep parsing aligned.
            if "R" in xy or "C" in xy:
                if index >= len(parts):
                    raise RuntimeError("UNPARSEABLE_GIT_STATUS")
                index += 1
            records.append((xy, path.replace("\\", "/")))
        return records

    @classmethod
    def _is_allowed(cls, relpath: str) -> bool:
        path = PurePosixPath(relpath)
        if relpath in cls.EXACT_FILES:
            return True
        if len(path.parts) < 2:
            return False
        suffixes = cls.ALLOWED_SUFFIXES.get(path.parts[0])
        return bool(suffixes and path.suffix.lower() in suffixes)

    def build_manifest(self) -> Dict[str, Any]:
        """Return the precise admissible delta and every excluded dirty path."""
        admitted: List[Dict[str, str]] = []
        excluded: List[Dict[str, str]] = []
        for xy, relpath in self._parse_status():
            # Git porcelain represents an entirely-untracked directory as one
            # ``?? directory/`` record.  Expand it only when its root is a
            # motherplate root; never recursively inspect excluded material.
            if xy == "??" and relpath.endswith("/"):
                root = self.repo_path / relpath
                top_level = PurePosixPath(relpath).parts[0] if PurePosixPath(relpath).parts else ""
                if top_level in self.ALLOWED_SUFFIXES and root.is_dir():
                    for candidate in sorted(root.rglob("*")):
                        if not candidate.is_file() or candidate.is_symlink():
                            continue
                        candidate_rel = candidate.relative_to(self.repo_path).as_posix()
                        if self._is_allowed(candidate_rel):
                            admitted.append(
                                {
                                    "path": candidate_rel,
                                    "status": xy,
                                    "sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
                                }
                            )
                        else:
                            excluded.append({"path": candidate_rel, "status": xy, "reason": "OUTSIDE_MOTHERPLATE_ALLOWLIST"})
                    continue
                excluded.append({"path": relpath, "status": xy, "reason": "OUTSIDE_MOTHERPLATE_ALLOWLIST"})
                continue
            if not self._is_allowed(relpath):
                excluded.append({"path": relpath, "status": xy, "reason": "OUTSIDE_MOTHERPLATE_ALLOWLIST"})
                continue
            file_path = self.repo_path / relpath
            if not file_path.is_file():
                excluded.append({"path": relpath, "status": xy, "reason": "NOT_A_REGULAR_FILE"})
                continue
            admitted.append(
                {
                    "path": relpath,
                    "status": xy,
                    "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                }
            )
        admitted.sort(key=lambda item: item["path"])
        canonical = json.dumps(admitted, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return {
            "files": admitted,
            "excluded": excluded,
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }

    def should_push(self) -> bool:
        if not self._last_push:
            return True
        try:
            return datetime.now() - datetime.fromisoformat(self._last_push) >= timedelta(minutes=self.debounce_minutes)
        except ValueError:
            return True

    def _select_manifest(self, manifest: Dict[str, Any], paths: Optional[Iterable[str]]) -> Dict[str, Any]:
        """Narrow a manifest to an explicitly reviewed atomic source pack.

        Supplying paths never expands authority: every requested path must be
        present in the current content manifest.  Remaining eligible files are
        disclosed as deferred rather than silently swept into the commit.
        """
        if paths is None:
            return manifest
        requested = sorted(set(paths))
        available = {entry["path"]: entry for entry in manifest["files"]}
        missing = sorted(set(requested) - set(available))
        if missing:
            raise RuntimeError(f"REQUESTED_PATH_NOT_IN_CURRENT_MANIFEST: {', '.join(missing)}")
        selected = [available[path] for path in requested]
        deferred = [
            {"path": entry["path"], "status": entry["status"], "reason": "DEFERRED_NOT_IN_EXPLICIT_SYNC_PACK"}
            for entry in manifest["files"]
            if entry["path"] not in requested
        ]
        canonical = json.dumps(selected, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return {
            "files": selected,
            "excluded": [*manifest["excluded"], *deferred],
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }

    def preflight(self, force: bool = False, paths: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "repo": str(self.repo_path), "remote": self.remote, "branch": self.branch,
            "at": datetime.now().isoformat(), "status": "BLOCKED", "reason": None,
            "changed_files": [], "excluded_files": [], "manifest_sha256": None,
            "local_head": None, "remote_head": None, "staged_files": [],
        }
        try:
            full_manifest = self.build_manifest()
            if paths is None and len(full_manifest["files"]) > self.max_automatic_files:
                result["changed_files"] = [item["path"] for item in full_manifest["files"]]
                result["excluded_files"] = full_manifest["excluded"]
                result["manifest_sha256"] = full_manifest["sha256"]
                result["reason"] = "EXPLICIT_SYNC_PACK_REQUIRED"
                return result
            manifest = self._select_manifest(full_manifest, paths)
            result["changed_files"] = [item["path"] for item in manifest["files"]]
            result["excluded_files"] = manifest["excluded"]
            result["manifest_sha256"] = manifest["sha256"]
            staged = [line for line in self._run_git("diff", "--cached", "--name-only").splitlines() if line]
            result["staged_files"] = staged
            if staged:
                result["reason"] = "PREEXISTING_STAGED_CHANGES"
            elif not result["changed_files"]:
                result["reason"] = "NO_ELIGIBLE_CHANGES"
            elif not force and not self.should_push():
                result["reason"] = "DEBOUNCED"
            else:
                result["local_head"] = self._run_git("rev-parse", "HEAD")
                result["remote_head"] = self._remote_head()
                if result["remote_head"] != result["local_head"]:
                    result["reason"] = "REMOTE_HEAD_DIFFERS_FROM_LOCAL_HEAD"
                else:
                    result["status"] = "READY"
                    result["reason"] = None
        except Exception as error:
            result["reason"] = f"PREFLIGHT_ERROR: {error}"
        return result

    def has_core_changes(self) -> bool:
        return bool(self.build_manifest()["files"])

    def get_changed_files(self) -> List[str]:
        return [entry["path"] for entry in self.build_manifest()["files"]]

    def sync(self, force: bool = False, paths: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        result = self.preflight(force=force, paths=paths)
        result.update({"added": False, "committed": False, "pushed": False, "commit_hash": None, "error": None, "skipped": False})
        if result["status"] != "READY":
            result["skipped"] = result.get("reason") == "DEBOUNCED"
            result["error"] = "no_changes" if result.get("reason") == "NO_ELIGIBLE_CHANGES" else result.get("reason")
            self._write_receipt(result)
            return result
        paths = result["changed_files"]
        try:
            self._run_git("add", "--", *paths)
            result["added"] = True
            staged = sorted(line for line in self._run_git("diff", "--cached", "--name-only").splitlines() if line)
            if staged != sorted(paths):
                raise RuntimeError("STAGED_MANIFEST_MISMATCH")
            manifest_short = result["manifest_sha256"][:12]
            self._run_git(
                "commit", "-m", f"core: civilization sync {manifest_short}",
                "-m", f"Manifest-SHA256: {result['manifest_sha256']}\nFiles: {len(paths)}",
            )
            result["committed"] = True
            result["commit_hash"] = self._run_git("rev-parse", "HEAD")
            self._run_git("push", self.remote, f"HEAD:{self.branch}")
            result["pushed"] = True
            result["status"] = "PUSHED"
            self._last_push = datetime.now().isoformat()
            result["reason"] = None
        except Exception as error:
            result["status"] = "FAILED"
            result["error"] = str(error)
        self._write_receipt(result)
        return result
