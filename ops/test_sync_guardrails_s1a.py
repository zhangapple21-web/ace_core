"""S1-A guardrail evidence. Every test here must pass without touching a real
repository, a real remote, or the production tree.

Run: py -3 -m pytest ops/test_sync_guardrails_s1a.py -q
"""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from core import sync_guardrails as g
from core.sync_manager import SyncManager


# ---------------------------------------------------------------- 1. symlink
def test_symlink_escape_is_refused(tmp_path):
    """A symlink that points outside the repository must not be followed."""
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / "docs").mkdir()
    (outside / "payload.md").write_text("secret place", encoding="utf-8")

    link = repo / "docs" / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this host")

    with pytest.raises(g.SyncRefused) as refusal:
        g.check_target_path("docs/link/payload.md", repo)
    assert "escapes repository root" in str(refusal.value)


def test_symlink_that_stays_inside_is_allowed(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs" / "real").mkdir(parents=True)
    (repo / "docs" / "real" / "note.md").write_text("fine", encoding="utf-8")
    link = repo / "docs" / "alias"
    try:
        link.symlink_to(repo / "docs" / "real", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this host")

    resolved = g.check_target_path("docs/alias/note.md", repo)
    assert resolved.endswith("note.md")


# ------------------------------------------------------------- 2. Tier1 write
@pytest.mark.parametrize(
    "target",
    [
        "00_ROOT/PRINCIPLES.md",
        "00_root/architecture.md",
        "01_CORE/anything.py",
        "04_PROTOCOLS/new.md",
        "core/governor.py",
        "06_RUNTIME/state.json",
        "09_KNOWLEDGE/EXP-x.json",
        "task_pool/pending/x.json",
        "07_SANDBOX/free_research/x.json",
        "08_GOVERNANCE/decision.json",
        "civilization_assets/lineage.json",
        "lineage/root.json",
    ],
)
def test_tier1_and_runtime_writes_are_refused(tmp_path, target):
    repo = tmp_path / "repo"
    for part in target.split("/"):
        (repo / part).mkdir(parents=True, exist_ok=True)
    with pytest.raises(g.SyncRefused):
        g.check_target_path(target, repo)


def test_allowed_prefix_is_accepted(tmp_path):
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "ok.md").write_text("fine", encoding="utf-8")
    assert g.check_target_path("docs/ok.md", repo) == "docs/ok.md"


# ------------------------------------------------- 3. staged index mismatch
def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def test_extra_staged_file_aborts_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "intended.md").write_text("one", encoding="utf-8")
    (repo / "smuggled.md").write_text("two", encoding="utf-8")
    _git(repo, "add", "intended.md")
    _git(repo, "add", "smuggled.md")  # someone staged this before us

    with pytest.raises(g.SyncRefused) as refusal:
        g.check_staged_matches_intended(repo, ["intended.md"])
    assert "staged_index_mismatch" in str(refusal.value)


def test_matching_staged_index_passes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "intended.md").write_text("one", encoding="utf-8")
    _git(repo, "add", "intended.md")
    g.check_staged_matches_intended(repo, ["intended.md"])


def test_git_ls_files_failure_fails_closed(tmp_path):
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    with pytest.raises(g.SyncRefused):
        g.git_tracked_files(empty)


# -------------------------------------------------- 4. push stays switched off
def test_push_is_never_called_when_disabled(tmp_path):
    manager = SyncManager(data_dir=str(tmp_path / "data"), curator_secret="s")
    assert manager.dry_run is True
    assert manager.push_enabled is False

    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.md").write_text("seed", encoding="utf-8")
    _git(repo, "add", "seed.md")
    _git(repo, "commit", "-m", "seed")
    manager.repo_map = {"ace_core": repo}

    called = []
    with mock.patch.object(
        manager, "_run_git", side_effect=lambda *a, **k: called.append(a) or (0, "", "")
    ), mock.patch.object(manager, "_has_remote", return_value=True):
        result = manager._sync_repo(
            "ace_core",
            [{"action": "create", "source_path": str(tmp_path / "src.md"),
              "target_path": "docs/src.md"}],
            {},
        )
    assert result.action == "dry_run"
    assert not any("push" in " ".join(str(x) for x in call) for call in called)


def test_dry_run_leaves_nothing_behind(tmp_path):
    manager = SyncManager(data_dir=str(tmp_path / "data"), curator_secret="s")
    source = tmp_path / "src.md"
    source.write_text("payload", encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    (repo / "seed.md").write_text("seed", encoding="utf-8")
    _git(repo, "add", "seed.md")
    _git(repo, "commit", "-m", "seed")

    manager.repo_map = {"ace_core": repo}
    before_files = sorted(p.name for p in repo.iterdir())
    before_log = _git(repo, "log", "--oneline").stdout
    before_diff = _git(repo, "status", "--porcelain").stdout

    result = manager._sync_repo(
        "ace_core",
        [{"action": "create", "source_path": str(source), "target_path": "docs/new.md"}],
        {},
    )

    assert result.action == "dry_run"
    assert not (repo / "docs" / "new.md").exists()
    assert sorted(p.name for p in repo.iterdir()) == before_files
    assert _git(repo, "log", "--oneline").stdout == before_log
    assert _git(repo, "status", "--porcelain").stdout == before_diff


# --------------------------- 5. ace_core still refused with secrets check off
def test_ace_core_refused_without_the_secret_check(tmp_path, monkeypatch):
    """tracks_secrets must not be the only thing standing in the way."""
    monkeypatch.setattr(g, "SECRET_TRACKED_PATTERNS", ())
    assert g.SECRET_TRACKED_PATTERNS == ()

    repo = tmp_path / "repo"
    repo.mkdir()

    # (a) the path prefixes refuse independently of any repo-level check.
    for target in ["09_KNOWLEDGE//EXP-x.json", "core//governor.py", "00_ROOT/PRINCIPLES.md"]:
        with pytest.raises(g.SyncRefused):
            g.check_target_path(target, repo)

    # (b) and a repo name that is not allowlisted is refused on its own.
    with pytest.raises(g.SyncRefused) as refusal:
        g.check_repo_allowed("mine-seed-credentials", tracked_files=["README.md"])
    assert "repo_name_denied" in str(refusal.value)

    # (c) an unknown repository is refused even when it tracks nothing.
    with pytest.raises(g.SyncRefused) as refusal:
        g.check_repo_allowed("some_other_repo", tracked_files=["README.md"])
    assert "repo_not_allowlisted" in str(refusal.value)


def test_allowlist_can_be_empty(tmp_path, monkeypatch):
    """With no approved repository, every repository is refused."""
    monkeypatch.setattr(g, "ALLOWED_TARGET_REPOS", ())
    with pytest.raises(g.SyncRefused):
        g.check_repo_allowed("ace_core", tracked_files=["README.md"])