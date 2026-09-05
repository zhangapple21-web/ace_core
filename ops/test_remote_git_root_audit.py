import subprocess
from pathlib import Path

from remote_git_root_audit import audit_repo, discover_repositories


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


def test_matching_clean_checkout_is_recoverable(tmp_path):
    work, _bare = _repo(tmp_path)
    result = audit_repo(work)
    assert result.state == "MATCH_CLEAN"
    assert result.local_head == result.remote_head
    assert result.dirty_entries == 0


def test_matching_commit_with_dirty_worktree_is_not_a_complete_root(tmp_path):
    work, _bare = _repo(tmp_path)
    (work / "local-only.txt").write_text("not pushed\n", encoding="utf-8")
    result = audit_repo(work)
    assert result.state == "MATCH_DIRTY"
    assert result.dirty_entries == 1


def test_remote_drift_is_reported_without_guessing_ancestry(tmp_path):
    work, bare = _repo(tmp_path)
    second = tmp_path / "second"
    _git(tmp_path, "clone", "--branch", "main", str(bare), str(second))
    _git(second, "config", "user.email", "audit@example.invalid")
    _git(second, "config", "user.name", "Audit")
    (second / "README.md").write_text("remote change\n", encoding="utf-8")
    _git(second, "add", "README.md")
    _git(second, "commit", "-m", "remote change")
    _git(second, "push", "origin", "main")
    result = audit_repo(work)
    assert result.state == "DRIFT"
    assert result.local_head != result.remote_head


def test_missing_remote_is_fail_closed(tmp_path):
    root = tmp_path / "plain"
    _git(tmp_path, "init", str(root))
    result = audit_repo(root)
    assert result.state == "NO_REMOTE"
    assert result.remote_url == ""


def test_discovery_stops_at_git_roots(tmp_path):
    work, _bare = _repo(tmp_path)
    nested = work / "nested"
    nested.mkdir()
    _git(nested, "init")
    found = discover_repositories(tmp_path)
    assert work.resolve() in found
    assert nested.resolve() not in found
