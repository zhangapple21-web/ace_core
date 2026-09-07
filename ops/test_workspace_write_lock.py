import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_workspace_write_lock_context_manager_releases_on_exception(tmp_path):
    from core.workspace_write_lock import WorkspaceWriteLock

    try:
        with WorkspaceWriteLock(tmp_path, owner_id="window-a"):
            assert (tmp_path / ".workspace.write.lock").exists()
            raise RuntimeError("abort")
    except RuntimeError:
        pass

    assert not (tmp_path / ".workspace.write.lock").exists()


def test_workspace_write_lock_reclaims_pid_reuse_owner(tmp_path, monkeypatch):
    from core.workspace_write_lock import WorkspaceWriteLock

    lock_file = tmp_path / ".workspace.write.lock"
    lock_file.write_text(json.dumps({
        "pid": 42,
        "owner_id": "stale-window",
        "run_id": "old-run",
        "process_started_at": 1.0,
        "token": "stale-token",
        "created_at": 1.0,
    }), encoding="utf-8")
    current = WorkspaceWriteLock(tmp_path, owner_id="window-a")
    original_owner_alive = current._owner_alive
    monkeypatch.setattr(current, "_process_started_at", lambda pid: 2.0)
    monkeypatch.setattr(current, "_owner_alive", original_owner_alive)

    result = current.acquire()

    assert result["acquired"] is True
    assert result["owner"]["owner_id"] == "window-a"
    current.release()


def test_workspace_write_lock_excludes_an_active_owner(tmp_path):
    from core.workspace_write_lock import WorkspaceWriteLock

    first = WorkspaceWriteLock(tmp_path, owner_id="window-a")
    second = WorkspaceWriteLock(tmp_path, owner_id="window-b")

    assert first.acquire()["acquired"] is True
    try:
        rejected = second.acquire()
        assert rejected["acquired"] is False
        assert rejected["reason"] == "workspace_write_locked"
        assert rejected["owner"]["owner_id"] == "window-a"
        assert rejected["lock_file"] == str(tmp_path / ".workspace.write.lock")
        assert rejected["recommendation"] == "wait_for_current_owner_or_verify_stale_lock"
    finally:
        first.release()


def test_workspace_write_lock_release_is_token_fenced(tmp_path):
    from core.workspace_write_lock import WorkspaceWriteLock

    first = WorkspaceWriteLock(tmp_path, owner_id="window-a")
    second = WorkspaceWriteLock(tmp_path, owner_id="window-b")

    assert first.acquire()["acquired"] is True
    second.token = "incorrect-token"
    second.release()
    assert first.lock_file.exists()
    first.release()


def test_workspace_write_lock_reclaims_only_a_dead_owner(tmp_path, monkeypatch):
    from core.workspace_write_lock import WorkspaceWriteLock

    lock_file = tmp_path / ".workspace.write.lock"
    lock_file.write_text(
        json.dumps({
            "pid": 99999999,
            "owner_id": "stale-window",
            "token": "stale-token",
            "created_at": 1,
        }),
        encoding="utf-8",
    )
    current = WorkspaceWriteLock(tmp_path, owner_id="window-a")
    monkeypatch.setattr(current, "_owner_alive", lambda owner: False)

    result = current.acquire()

    assert result["acquired"] is True
    assert result["owner"]["owner_id"] == "window-a"


def test_workspace_write_lock_keeps_malformed_record_fail_closed(tmp_path):
    from core.workspace_write_lock import WorkspaceWriteLock

    lock_file = tmp_path / ".workspace.write.lock"
    lock_file.write_text("{", encoding="utf-8")

    result = WorkspaceWriteLock(tmp_path, owner_id="window-a").acquire()

    assert result["acquired"] is False
    assert result["reason"] == "workspace_write_locked"
    assert result["owner"] == {}


def test_daemon_workspace_lock_blocks_a_second_daemon(tmp_path):
    from ace_daemon import AceDaemon

    first = AceDaemon(tmp_path, {})
    second = AceDaemon(tmp_path, {})
    first.run_id = "first-run"
    second.run_id = "second-run"

    assert first._acquire_workspace_write_lock() is True
    try:
        assert second._acquire_workspace_write_lock() is False
        assert second.workspace_lock_conflict["reason"] == "workspace_write_locked"
        assert second.workspace_lock_conflict["owner"]["owner_id"] == "ace_daemon"
        assert second.workspace_lock_conflict["owner"]["run_id"] == "first-run"
    finally:
        first._release_workspace_write_lock()

    assert second._acquire_workspace_write_lock() is True
    second._release_workspace_write_lock()


def test_daemon_run_releases_workspace_lock_when_startup_raises(tmp_path):
    from ace_daemon import AceDaemon

    daemon = AceDaemon(tmp_path, {})

    def fail_startup(reason):
        raise RuntimeError("startup failed")

    daemon.heartbeat.beat = fail_startup
    try:
        daemon.run_daemon(max_iterations=1, dry_run=True)
    except RuntimeError:
        pass

    assert not (tmp_path / ".workspace.write.lock").exists()


def test_daemon_run_reports_workspace_lock_conflict_without_running(tmp_path):
    from ace_daemon import AceDaemon

    holder = AceDaemon(tmp_path, {})
    contender = AceDaemon(tmp_path, {})
    holder.run_id = "holder-run"

    assert holder._acquire_workspace_write_lock() is True
    try:
        result = contender.run_daemon(max_iterations=1, dry_run=True)
    finally:
        holder._release_workspace_write_lock()

    assert result["stop_reason"] == "workspace_write_locked"
    assert result["workspace_lock_conflict"]["owner"]["run_id"] == "holder-run"
