import json
import subprocess
from pathlib import Path

from remote_recovery_inventory import inventory_remote


def _git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def _repo(tmp_path: Path):
    bare = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "init", str(work))
    _git(work, "config", "user.email", "audit@example.invalid")
    _git(work, "config", "user.name", "Audit")
    (work / "README.md").write_text("base\n", encoding="utf-8")
    _git(work, "add", "README.md")
    _git(work, "commit", "-m", "base")
    _git(work, "branch", "-M", "main")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-u", "origin", "main")
    return work, bare


def test_remote_only_root_is_recoverable_but_not_a_local_claim(tmp_path):
    work, bare = _repo(tmp_path)
    clone = tmp_path / "clone"
    result = inventory_remote("example/repo", str(bare), local_path=clone)
    assert result.recovery_state == "REMOTE_ONLY"
    assert result.remote_head


def test_dirty_checkout_is_not_complete_recovery_root(tmp_path):
    work, bare = _repo(tmp_path)
    (work / "local-only.txt").write_text("not pushed\n", encoding="utf-8")
    result = inventory_remote("example/repo", str(bare), local_path=work)
    assert result.recovery_state == "MATCH_DIRTY"
    assert result.dirty_entries == 1


def test_protection_and_visibility_remain_explicit_metadata(tmp_path):
    _work, bare = _repo(tmp_path)
    result = inventory_remote(
        "example/repo",
        str(bare),
        protection_state="UNKNOWN_CONTROL_PLANE",
        visibility_state="PUBLIC_OBSERVED",
    )
    assert result.protection_state == "UNKNOWN_CONTROL_PLANE"
    assert result.visibility_state == "PUBLIC_OBSERVED"
