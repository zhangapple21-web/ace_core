#!/usr/bin/env python3
import json
import os
import signal
import subprocess
import sys
import tempfile
import time

import pytest
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def model_task_admission():
    return {
        "source_type": "maintenance",
        "source_ref": "model-pipeline-test",
        "why_now": "A persisted production trace needs classification.",
        "evidence": [{"source_ref": "runtime:trace"}],
        "expected_result": "A read-only metric summary.",
        "verification_method": "Inspect the metric result.",
        "risk": "Test-only fixture.",
        "estimated_scope": "one metric method",
    }


def test_daemon_import_and_construction():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        assert callable(daemon.run_daemon)
        assert daemon.task_pool is not None


def test_daemon_defaults_to_analysis_only_repository_curation():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        (base_dir / ".git").mkdir()

        daemon = AceDaemon(base_dir, {})

        assert daemon.repository_curator is not None
        assert daemon.repository_curator.sync_manager is None


def test_daemon_service_entrypoint():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "ace.py"),
                "daemon",
                "--serve",
                "--dry-run",
                "--max-iter",
                "1",
                "--interval",
                "0",
            ],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr or result.stdout


def test_status_command_uses_daemon_runtime():
    with tempfile.TemporaryDirectory() as temp_dir:
        result = subprocess.run(
            [sys.executable, str(ROOT / "ace.py"), "status"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        assert '"task_pool"' in result.stdout


def test_daemon_process_lock_excludes_second_daemon():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        first = AceDaemon(Path(temp_dir), {})
        second = AceDaemon(Path(temp_dir), {})

        assert first._acquire_daemon_lock()
        try:
            assert not second._acquire_daemon_lock()
        finally:
            first._release_daemon_lock()

        assert second._acquire_daemon_lock()
        second._release_daemon_lock()


def test_daemon_lock_binds_the_current_run_identity():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.run_id = "current-production-run"

        assert daemon._acquire_daemon_lock()
        try:
            owner = json.loads(daemon.daemon_lock_file.read_text(encoding="utf-8"))
            assert owner["run_id"] == "current-production-run"
        finally:
            daemon._release_daemon_lock()


def test_daemon_lock_rechecks_incomplete_metadata_before_reclaiming(monkeypatch):
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.daemon_lock_file.write_text("{", encoding="utf-8")
        owner = json.dumps({"pid": os.getpid(), "token": "active", "created_at": time.time()})
        reads = iter(["{", owner])
        original_read_text = Path.read_text

        def delayed_read_text(path, *args, **kwargs):
            if path == daemon.daemon_lock_file:
                return next(reads)
            return original_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", delayed_read_text)

        assert not daemon._acquire_daemon_lock()
        assert daemon.daemon_lock_file.exists()


def test_daemon_lock_releases_when_startup_raises():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})

        def fail_startup(reason):
            raise RuntimeError("startup failed")

        daemon.heartbeat.beat = fail_startup
        try:
            daemon.run_daemon(max_iterations=1, dry_run=True)
        except RuntimeError:
            pass

        assert not daemon.daemon_lock_file.exists()


def test_daemon_startup_persists_current_run_identity_before_first_cycle():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.run_id = "current-production-run"

        daemon._checkpoint_startup()

        state = json.loads(daemon.state_file.read_text(encoding="utf-8"))
        assert state["pid"] == os.getpid()
        assert state["run_id"] == "current-production-run"
        assert state["run_status"] == "alive"
        assert state["run_started_at"]


def test_graceful_shutdown_does_not_count_as_death_and_releases_locks():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.request_shutdown("test_graceful_stop")
        death_count_before = daemon.heartbeat.get_status()["death_count"]

        result = daemon.run_daemon(interval_seconds=0, dry_run=True)
        heartbeat = daemon.heartbeat.get_status()
        state = json.loads(daemon.state_file.read_text(encoding="utf-8"))

        assert result["stop_reason"] == "test_graceful_stop"
        assert heartbeat["status"] == "stopping"
        assert heartbeat["death_count"] == death_count_before
        assert heartbeat["last_exit_reason"] == "test_graceful_stop"
        assert heartbeat["last_exit_time"]
        assert heartbeat["pid"] == os.getpid()
        assert heartbeat["run_id"]
        assert state["last_exit_reason"] == "test_graceful_stop"
        assert state["last_exit_time"]
        assert not daemon.daemon_lock_file.exists()
        assert not daemon.lifecycle_lock_file.exists()


def test_fatal_shutdown_marks_heartbeat_dead_and_increments_death_count():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        death_count_before = daemon.heartbeat.get_status()["death_count"]

        def fail_diagnosis(base_dir):
            raise RuntimeError("test fatal failure")

        daemon.self_healing.diagnose = fail_diagnosis
        result = daemon.run_daemon(interval_seconds=0, max_iterations=1, dry_run=True)
        heartbeat = daemon.heartbeat.get_status()

        assert result["stop_reason"] == "fatal_error: test fatal failure"
        assert result["final_health"] is None
        assert heartbeat["status"] == "dead"
        assert heartbeat["death_count"] == death_count_before + 1
        assert heartbeat["last_death_reason"] == "fatal_error: test fatal failure"


def test_shutdown_signal_handler_only_requests_shutdown():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon._handle_shutdown_signal(signal.SIGTERM, None)

        assert daemon.shutdown_event.is_set()
        assert daemon.shutdown_reason == ""
        assert daemon.run_daemon(interval_seconds=0, dry_run=True)["stop_reason"] == "shutdown_requested"


def test_dead_heartbeat_is_not_reported_alive():
    from core.heartbeat import Heartbeat

    with tempfile.TemporaryDirectory() as temp_dir:
        heartbeat = Heartbeat(Path(temp_dir))
        heartbeat.beat(reason="startup")
        heartbeat.mark_dead(reason="test_stop")

        assert not heartbeat.is_alive()
        assert not heartbeat.get_status()["is_alive"]


def test_recent_heartbeat_for_missing_process_is_persisted_stale():
    from core.heartbeat import Heartbeat

    with tempfile.TemporaryDirectory() as temp_dir:
        heartbeat = Heartbeat(Path(temp_dir))
        heartbeat.status.update(
            {
                "status": "alive",
                "pid": 999999,
                "run_id": "host-terminated-recent-run",
                "last_beat": datetime.now().isoformat(),
            }
        )
        heartbeat._save()

        status = heartbeat.get_status(max_idle_seconds=60)

        assert status["status"] == "stale"
        assert not status["is_alive"]
        assert status["last_exit_reason"] == "host_termination"
        assert json.loads(heartbeat.heartbeat_file.read_text(encoding="utf-8"))["status"] == "stale"


def test_expired_heartbeat_for_missing_process_is_persisted_stale():
    from core.heartbeat import Heartbeat

    with tempfile.TemporaryDirectory() as temp_dir:
        heartbeat = Heartbeat(Path(temp_dir))
        heartbeat.status.update(
            {
                "status": "alive",
                "pid": 999999,
                "run_id": "host-terminated-run",
                "last_beat": (datetime.now() - timedelta(seconds=61)).isoformat(),
            }
        )
        heartbeat._save()

        status = heartbeat.get_status(max_idle_seconds=60)

        assert status["status"] == "stale"
        assert not status["is_alive"]
        assert status["last_exit_reason"] == "host_termination"
        assert json.loads(heartbeat.heartbeat_file.read_text(encoding="utf-8"))["status"] == "stale"


def test_health_checker_reports_missing_runtime_process_as_error(monkeypatch):
    from core.heartbeat import Heartbeat
    from ops import health_check

    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        heartbeat = Heartbeat(runtime_dir)
        heartbeat.status.update(
            {
                "status": "alive",
                "pid": 999999,
                "run_id": "health-check-host-termination",
                "last_beat": datetime.now().isoformat(),
            }
        )
        heartbeat._save()
        monkeypatch.setattr(health_check, "BASE_DIR", Path(temp_dir))

        checker = health_check.HealthChecker()
        checker._check_runtime_liveness()

        assert checker.errors[0]["name"] == "daemon心跳存活"
        assert json.loads(heartbeat.heartbeat_file.read_text(encoding="utf-8"))["status"] == "stale"


def test_health_checker_rejects_live_non_ace_runtime_process(monkeypatch):
    from core.heartbeat import Heartbeat
    from ops import health_check

    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        heartbeat = Heartbeat(runtime_dir)
        heartbeat.status.update(
            {
                "status": "alive",
                "pid": os.getpid(),
                "run_id": "health-check-non-ace-process",
                "last_beat": datetime.now().isoformat(),
            }
        )
        heartbeat._save()
        monkeypatch.setattr(health_check, "BASE_DIR", Path(temp_dir))
        monkeypatch.setattr(health_check, "_process_command_line", lambda pid: "python unrelated.py")

        checker = health_check.HealthChecker()
        checker._check_runtime_liveness()

        assert checker.errors[0]["name"] == "daemon进程归属"


def test_health_checker_accepts_ace_cli_daemon_process(monkeypatch):
    from core.heartbeat import Heartbeat
    from ops import health_check

    with tempfile.TemporaryDirectory() as temp_dir:
        runtime_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        heartbeat = Heartbeat(runtime_dir)
        heartbeat.status.update(
            {
                "status": "alive",
                "pid": os.getpid(),
                "run_id": "health-check-ace-cli-process",
                "last_beat": datetime.now().isoformat(),
            }
        )
        heartbeat._save()
        monkeypatch.setattr(health_check, "BASE_DIR", Path(temp_dir))
        monkeypatch.setattr(
            health_check,
            "_process_command_line",
            lambda pid: 'python "C:/tmp/ace_core/ace.py" daemon --serve',
        )

        checker = health_check.HealthChecker()
        checker._check_runtime_liveness()

        assert checker.info[-1]["name"] == "daemon进程归属"


def test_daemon_recovers_stale_lock_after_forced_process_termination():
    with tempfile.TemporaryDirectory() as temp_dir:
        daemon_root = Path(temp_dir)
        start_code = (
            "from pathlib import Path; "
            "from ace_daemon import AceDaemon; "
            f"AceDaemon(Path({str(daemon_root)!r}), {{}}).run_daemon("
            "interval_seconds=60, dry_run=True)"
        )
        process = subprocess.Popen(
            [sys.executable, "-c", start_code],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        lock_file = daemon_root / "06_RUNTIME" / "ace" / "data" / "memory" / ".daemon.lock"
        deadline = time.monotonic() + 15
        try:
            while not lock_file.exists() and time.monotonic() < deadline:
                time.sleep(0.1)

            assert lock_file.exists()
            process.kill()
            process.wait(timeout=15)
            assert lock_file.exists()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)

        recover_code = (
            "from pathlib import Path; "
            "from ace_daemon import AceDaemon; "
            f"AceDaemon(Path({str(daemon_root)!r}), {{}}).run_daemon("
            "interval_seconds=0, max_iterations=1, dry_run=True)"
        )
        recovered = subprocess.run(
            [sys.executable, "-c", recover_code],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        assert recovered.returncode == 0, recovered.stderr or recovered.stdout
        assert not lock_file.exists()


def test_atomic_task_claim_preserves_valid_lease_and_recovers_stale_lease():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("lease-protected task", priority="high", creator="test")
        first = pool.claim_task(task.task_id, "worker-a", lease_seconds=60)
        second = pool.claim_task(task.task_id, "worker-b", lease_seconds=60)
        assert first is not None
        assert second is None

        renewed = pool.renew_lease(task.task_id, "worker-a", first.claim_id, 60)
        assert renewed is not None
        assert pool.reclaim_stale_leases() == []

        expired_at = (datetime.now() + timedelta(seconds=61)).isoformat()
        recovered = pool.reclaim_stale_leases(expired_at)
        assert [item.task_id for item in recovered] == [task.task_id]
        recovered_task = pool.load_task(task.task_id)
        assert recovered_task.status == "pending"
        assert recovered_task.claim_id == ""
        assert recovered_task.lease_owner == ""


def test_recovery_requeues_orphaned_active_task_without_lease():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("orphaned active task", creator="test")
        task.status = "active"
        pool.move_task(task.task_id, "active", task=task)

        recovered = pool.reclaim_stale_leases()

        assert [item.task_id for item in recovered] == [task.task_id]
        stored = pool.load_task(task.task_id)
        assert stored.status == "pending"
        assert stored.claim_id == ""
        assert stored.lease_owner == ""
        assert stored.audit_log[-1]["reason"] == "orphaned_active_recovered"


def test_stale_lock_file_does_not_block_task_claim():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("recover abandoned lock", creator="test")
        pool.lock_file.write_text("999999999", encoding="ascii")
        os.utime(pool.lock_file, (0, 0))

        claimed = pool.claim_task(task.task_id, "worker-a", lease_seconds=60)
        assert claimed is not None
        assert claimed.lease_owner == "worker-a"


def test_retry_backoff_prevents_early_reclaim():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("retry later", creator="test")
        pool.fail_task(task.task_id, "temporary provider failure", failure_type="retryable")

        assert pool.claim_task(task.task_id, "worker-a", lease_seconds=60) is None

        stored = pool.load_task(task.task_id)
        stored.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        pool.update_task(stored)
        assert pool.claim_task(task.task_id, "worker-a", lease_seconds=60) is not None


def test_recovery_keeps_latest_duplicate_task_state():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("interrupted transition", creator="test")
        duplicate = task.to_dict()
        duplicate["status"] = "active"
        duplicate["assignee"] = "worker-a"
        duplicate_path = pool.pool_dir / "active" / f"{task.task_id}.json"
        duplicate_path.write_text(json.dumps(duplicate), encoding="utf-8")
        latest_timestamp = datetime.now().timestamp() + 60
        os.utime(duplicate_path, (latest_timestamp, latest_timestamp))

        recovered_pool = TaskPool(temp_dir)
        recovered = recovered_pool.load_task(task.task_id)
        assert recovered.status == "active"
        assert recovered.assignee == "worker-a"
        assert not (recovered_pool.pool_dir / "pending" / f"{task.task_id}.json").exists()


def test_researchers_use_atomic_task_claims():
    from core.task import TaskPool
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        pool.create_task("single owner task", priority="high", creator="test")
        first = Researcher(pool).pick_up_task(priority="high")
        second = Researcher(pool).pick_up_task(priority="high")

        assert first is not None
        assert first.lease_owner == "researcher"
        assert second is None


def test_daemon_reclaims_stale_leases_before_work():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        task = daemon.task_pool.create_task("abandoned worker task", creator="test")
        claimed = daemon.task_pool.claim_task(task.task_id, "worker-a", lease_seconds=1)
        assert claimed is not None

        recovered = daemon.recover_task_pool(
            now=(datetime.now() + timedelta(seconds=2)).isoformat()
        )
        assert recovered == [task.task_id]
        assert daemon.task_pool.load_task(task.task_id).status == "pending"


def test_researcher_failure_is_persisted_for_retry():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        task = daemon.task_pool.create_task("broken researcher task", priority="high", creator="test")
        task.title = None
        daemon.task_pool.update_task(task)

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        assert stored.status == "pending"
        assert stored.retry_count == 1
        assert stored.failure_reason
        assert stored.lease_owner == ""


def test_researcher_renews_claim_before_researching():
    from core.task import TaskPool
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("renew the research lease", priority="high", creator="test")
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=1)
        assert claimed is not None

        Researcher(pool).research_task(claimed)

        stored = pool.load_task(task.task_id)
        assert stored.status == "review"
        assert any(event["event"] == "lease_renewed" for event in stored.audit_log)


def test_stale_claim_cannot_overwrite_new_owner():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("fenced task", creator="test")
        stale = pool.claim_task(task.task_id, "worker-a", lease_seconds=1)
        assert stale is not None
        pool.reclaim_stale_leases(now=(datetime.now() + timedelta(seconds=2)).isoformat())
        current = pool.claim_task(task.task_id, "worker-b", lease_seconds=60)
        assert current is not None

        stale.title = "stale overwrite"
        assert not pool.update_task(stale)
        assert pool.move_task(stale.task_id, "review", actor="worker-a", task=stale) is None

        stored = pool.load_task(task.task_id)
        assert stored.lease_owner == "worker-b"
        assert stored.title == "fenced task"


def test_task_state_machine_blocks_governance_bypasses_and_preserves_archives():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("state-machine task", creator="test")

        assert pool.move_task(task.task_id, "archived", actor="bypass") is None
        assert pool.load_task(task.task_id).status == "pending"

        active = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        assert active is not None
        assert pool.move_task(task.task_id, "approved", actor="bypass", task=active) is None
        assert pool.move_task(task.task_id, "review", actor="researcher", task=active) is not None
        review = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "approved", actor="validator", task=review) is not None
        approved = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "archived", actor="archivist", task=approved) is not None

        archived = pool.load_task(task.task_id)
        archived.last_referenced_at = (datetime.now() - timedelta(days=31)).isoformat()
        assert pool.update_task(archived)
        assert pool.check_graveyard() == []
        assert pool.load_task(task.task_id).status == "archived"


def test_external_blocks_do_not_auto_release():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("external gate", creator="test")
        pool.block_task(
            task.task_id,
            "market closed",
            block_type="external_condition_blocked",
        )
        blocked = pool.load_task(task.task_id)
        assert blocked.block_type == "external_condition_blocked"
        assert pool.check_depends_satisfied(blocked)
        assert pool.unblock_ready_dependencies() == []


def test_graveyard_sweep_preserves_blocked_convergence_states():
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("awaiting external evidence", creator="test")
        pool.block_task(
            task.task_id,
            "waiting for external evidence",
            block_type="external_condition_blocked",
        )
        blocked = pool.load_task(task.task_id)
        blocked.last_referenced_at = (datetime.now() - timedelta(days=31)).isoformat()
        assert pool.update_task(blocked)

        assert pool.check_graveyard() == []
        preserved = pool.load_task(task.task_id)
        assert preserved.status == "blocked"
        assert preserved.block_type == "external_condition_blocked"


def test_archivist_preserves_task_fencing_on_archive():
    from core.task import TaskPool
    from core.task_roles import Archivist

    class MemoryIndex:
        def __init__(self):
            self.entries = []

        def add(self, **entry):
            self.entries.append(entry)

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("fenced archival", creator="test")
        assert pool.move_task(task.task_id, "active", task=task) is not None
        active = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "review", task=active) is not None
        review = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "approved", task=review) is not None
        approved = pool.load_task(task.task_id)
        approved.guardian_decision = "experience"
        assert pool.update_task(approved)

        stale = pool.load_task(task.task_id)
        current = pool.load_task(task.task_id)
        current.claim_id = "current-claim"
        current.fencing_token = 2
        pool.update_task(current)
        stale.claim_id = "stale-claim"
        stale.fencing_token = 1
        memory_index = MemoryIndex()

        assert not Archivist(pool, memory_index=memory_index).archive_task(stale)
        assert pool.load_task(task.task_id).status == "approved"
        assert memory_index.entries == []


def test_archivist_requires_guardian_archive_decision():
    from core.task import TaskPool
    from core.task_roles import Archivist

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("unguarded archival", creator="test")
        assert pool.move_task(task.task_id, "active", task=task) is not None
        active = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "review", task=active) is not None
        review = pool.load_task(task.task_id)
        assert pool.move_task(task.task_id, "approved", task=review) is not None

        assert not Archivist(pool).archive_task(pool.load_task(task.task_id))
        assert pool.load_task(task.task_id).status == "approved"


def test_repeated_review_does_not_force_approval_without_passing_validation():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("insufficient reviewed evidence", creator="test")
        task.status = "review"
        task.review_count = 2
        task.hypothesis = "requires more evidence"
        task.evidence = [
            {"content": "A sufficiently detailed first evidence record." * 2},
            {"content": "A sufficiently detailed second evidence record." * 2},
        ]
        pool.move_task(task.task_id, "review", task=task)

        result = Validator(pool).validate_task(pool.load_task(task.task_id))

        assert not result["passed"]
        assert pool.load_task(task.task_id).status == "pending"


def test_validator_rework_returns_to_pending_with_retry_metadata():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("validator rework", creator="test")
        task.status = "review"
        task.hypothesis = "needs more evidence"
        task.evidence = [{"content": "first evidence" * 8}, {"content": "second evidence" * 8}]
        pool.move_task(task.task_id, "review", task=task)

        result = Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)

        assert not result["passed"]
        assert stored.status == "pending"
        assert stored.claim_id == ""
        assert stored.lease_owner == ""
        assert stored.retry_after
        assert stored.outputs["rework_reason"]
        assert stored.outputs["last_validator_result"]["review_count"] == 1
        assert pool.claim_task(stored.task_id, "researcher") is None


def test_validator_blocks_unchanged_evidence_after_review_limit():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("non convergent review", creator="test")
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "needs more evidence"
        task.evidence = [{"content": "first evidence" * 8}, {"content": "second evidence" * 8}]
        task.outputs["last_validated_evidence_signature"] = Validator.evidence_signature(task)
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        result = Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)

        assert not result["passed"]
        assert stored.status == "blocked"
        assert stored.block_type == "manual_gate_blocked"
        assert stored.outputs["last_validator_result"]["outcome"] == "blocked_non_convergent"


def test_validator_observes_non_convergent_external_research():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "external evidence loop",
            creator="test",
            tags=["external"],
        )
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "needs more evidence"
        task.evidence = [{"content": "first evidence" * 8}, {"content": "second evidence" * 8}]
        task.outputs["last_validated_evidence_signature"] = Validator.evidence_signature(task)
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)

        assert stored.status == "blocked"
        assert stored.block_type == "external_condition_blocked"
        assert stored.outputs["last_validator_result"]["outcome"] == "observe_non_convergent"


def test_validator_graveyards_explicit_permanent_dead_end_at_review_limit():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "permanent dead end",
            creator="test",
            tags=["permanent_dead_end"],
        )
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "needs more evidence"
        task.evidence = [{"content": "first evidence" * 8}, {"content": "second evidence" * 8}]
        task.outputs["last_validated_evidence_signature"] = Validator.evidence_signature(task)
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)

        assert stored.status == "graveyard"
        assert stored.outputs["last_validator_result"]["outcome"] == "graveyard_non_convergent"


def test_validator_allows_changed_evidence_to_reenter_research_after_review_limit():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("changed evidence", creator="test")
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "needs more evidence"
        task.evidence = [{"content": "current evidence" * 8}, {"content": "new evidence" * 8}]
        task.outputs["last_validated_evidence_signature"] = "different-evidence-signature"
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)
        stored.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        pool.update_task(stored)

        assert stored.status == "pending"
        assert stored.outputs["last_validator_result"]["outcome"] == "rework_pending"
        assert pool.claim_task(stored.task_id, "researcher") is not None


def test_validator_blocks_legacy_rework_signature_when_current_evidence_is_unchanged():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("legacy signature loop", creator="test")
        task.status = "review"
        task.review_count = 153
        task.hypothesis = "requires more evidence"
        task.counter_examples = ["existing counterexample"]
        task.evidence = [
            {"source": "runtime", "content": "same evidence" * 12},
            {"source": "runtime", "content": "independent evidence" * 12},
        ] * 200
        task.outputs["last_validator_result"] = {
            "outcome": "rework_pending",
            "evidence_signature": "legacy-unrecognized-signature",
        }
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        migrated = pool.load_task(task.task_id)

        assert migrated.status == "pending"
        assert migrated.outputs["last_validator_result"]["outcome"] == "rework_pending"
        assert migrated.outputs["last_validator_result"]["evidence_signature"] == Validator.evidence_signature(migrated)
        assert migrated.outputs["evidence_signature_version"] == Validator.EVIDENCE_SIGNATURE_VERSION

        migrated.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        pool.update_task(migrated)
        pool.move_task(migrated.task_id, "review", task=migrated)
        Validator(pool).validate_task(pool.load_task(migrated.task_id))
        stored = pool.load_task(migrated.task_id)

        assert stored.status == "blocked"
        assert stored.outputs["terminal_non_convergent"]
        assert stored.outputs["last_validator_result"]["outcome"] == "blocked_non_convergent"


def test_validator_blocks_semantically_unchanged_duplicate_evidence_at_review_limit():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("duplicate evidence loop", creator="test")
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "requires more evidence"
        task.evidence = [
            {"source": "runtime", "content": "same evidence" * 12},
            {"source": "runtime", "content": "independent evidence" * 12},
            {"source": "runtime", "content": "same evidence" * 12},
        ]
        previous = pool.load_task(task.task_id)
        previous.evidence = task.evidence[:2]
        task.outputs["last_validated_evidence_signature"] = Validator.evidence_signature(previous)
        task.outputs["last_validator_result"] = {
            "outcome": "rework_pending",
            "objections": ["未主动寻找反例，存在确认偏误风险"],
        }
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)

        assert stored.status == "blocked"
        assert stored.block_type == "manual_gate_blocked"
        assert stored.retry_after == ""
        assert pool.claim_task(stored.task_id, "researcher") is None


def test_non_convergent_terminal_block_cannot_be_reopened_or_claimed():
    from core.task import TaskPool
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("terminal non convergence", creator="test")
        task.status = "review"
        task.review_count = 3
        task.hypothesis = "requires more evidence"
        task.evidence = [
            {"content": "first evidence" * 12},
            {"content": "second evidence" * 12},
        ]
        task.outputs["last_validated_evidence_signature"] = Validator.evidence_signature(task)
        task.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)
        stored.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        pool.update_task(stored)

        assert stored.outputs["terminal_non_convergent"]
        assert pool.unblock_task(stored.task_id, actor="manual") is None
        assert pool.claim_task(stored.task_id, "researcher") is None


def test_researcher_yields_rework_high_to_untouched_high_after_streak_limit():
    from core.task import TaskPool
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        rework = pool.create_task("rework high", creator="test", priority="high")
        rework.rework_count = 2
        rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        pool.update_task(rework)
        untouched = pool.create_task("untouched high", creator="test", priority="high")

        claimed = Researcher(pool).pick_up_task(priority="any")
        stored_rework = pool.load_task(rework.task_id)

        assert claimed.task_id == untouched.task_id
        assert stored_rework.selection_trace[-1]["reason"] == "fairness_yield"


def test_researcher_yields_rework_high_to_untouched_medium_after_streak_limit():
    from core.task import TaskPool
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        rework = pool.create_task("rework high", creator="test", priority="high")
        rework.rework_count = 2
        rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        pool.update_task(rework)
        untouched = pool.create_task("untouched medium", creator="test", priority="medium")

        claimed = Researcher(pool).pick_up_task(priority="any")

        assert claimed.task_id == untouched.task_id


def test_backlog_watermark_suppresses_only_low_value_producers():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        for index in range(20):
            daemon.task_pool.create_task(f"backlog {index}", creator="test")

        policy = daemon._task_production_policy()

        assert policy["backlog_protected"]
        assert not policy["file_scanner"]
        assert not policy["observer"]
        assert policy["discovery"]
        assert not policy["task_creator"]
        assert policy["daily_learning"]
        assert policy["dependency_recovery"]


def test_task_installer_declares_boot_and_periodic_liveness_triggers():
    installer = (ROOT / "ops" / "install_tasks.ps1").read_text(encoding="utf-8")

    assert "New-ScheduledTaskTrigger -AtStartup" in installer
    assert "-RepetitionInterval (New-TimeSpan -Minutes 10)" in installer
    assert "-RestartCount 3" in installer
    assert "-ExecutionTimeLimit $executionTimeLimit" in installer


def test_self_healing_checks_current_task_pool_directory():
    from core.self_healing import SelfHealing
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(root / "task_pool")
        task = pool.create_task("stale active task", creator="test")
        task.status = "active"
        pool.move_task(task.task_id, "active", task=task)
        task_file = root / "task_pool" / "active" / f"{task.task_id}.json"
        payload = json.loads(task_file.read_text(encoding="utf-8"))
        payload["updated_at"] = (datetime.now() - timedelta(hours=2)).isoformat()
        task_file.write_text(json.dumps(payload), encoding="utf-8")

        issues = SelfHealing(root / "runtime").diagnose(root)["issues"]

        assert any(issue["type"] == "task_deadlock" for issue in issues)


def test_self_healing_recovers_current_task_pool_through_state_machine():
    from core.self_healing import SelfHealing
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(root / "task_pool")
        task = pool.create_task("recover stale active task", creator="test")
        task.status = "active"
        pool.move_task(task.task_id, "active", task=task)
        task_file = root / "task_pool" / "active" / f"{task.task_id}.json"
        payload = json.loads(task_file.read_text(encoding="utf-8"))
        payload["updated_at"] = (datetime.now() - timedelta(hours=2)).isoformat()
        task_file.write_text(json.dumps(payload), encoding="utf-8")

        result = SelfHealing(root / "runtime").heal(root)
        recovered = pool.load_task(task.task_id)

        assert any(
            issue["type"] == "task_deadlock"
            for issue in result["fixed_issues"]
        )
        assert recovered.status == "pending"
        assert recovered.retry_count == 1
        assert any(
            event["reason"] == "stale_active_recovered"
            for event in recovered.audit_log
        )


def test_legacy_archive_scripts_cannot_bypass_guardian_and_archivist():
    archive_source = (ROOT / "ops" / "auto_archive_approved.py").read_text(
        encoding="utf-8"
    )
    review_source = (ROOT / "ops" / "clear_review_queue.py").read_text(
        encoding="utf-8"
    )

    assert "from core.task_roles import Archivist" in archive_source
    assert "archive_task(task)" in archive_source
    assert 'move_task(task_id, "archived"' not in archive_source
    assert 'move_task(task_id, "approved"' not in review_source
    assert 'move_task(task_id, "archived"' not in review_source


def test_backup_covers_complete_task_pool_and_cleanup_preserves_records():
    backup_source = (ROOT / "ops" / "backup_data.py").read_text(encoding="utf-8")
    cleanup_source = (ROOT / "ops" / "cleanup_expired_tasks.py").read_text(
        encoding="utf-8"
    )

    assert 'base_dir / "task_pool"' in backup_source
    assert 'base_dir / "task_pool" / "archived"' not in backup_source
    assert "task_file.unlink()" not in cleanup_source


def test_run_once_exposes_lifecycle_execution_metrics():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.local_archaeologist = None
        daemon.web_scout = None
        daemon.decide_today_task = lambda: {
            "date": "2026-08-23",
            "scan_targets_count": 0,
            "actions": [],
        }
        daemon._run_task_lifecycle = lambda: {"researched": 2}

        result = daemon.run_once()

        assert result["auto_result"]["tasks_executed"] == 2


def test_run_once_persists_stage_progress_and_durations():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.local_archaeologist = None
        daemon.web_scout = None
        daemon.skill_generator = None
        daemon.repository_curator = None
        daemon.decide_today_task = lambda: {
            "date": "2026-08-23",
            "scan_targets_count": 0,
            "actions": [],
        }
        model_pipeline = {
            "reasoning_tasks_created": 1,
            "production_task_calls": 1,
            "providers": {"provider-a": 1},
        }
        daemon._run_task_lifecycle = lambda: {
            "researched": 0,
            "model_pipeline": model_pipeline,
        }

        daemon.run_once()

        state = json.loads(daemon.state_file.read_text(encoding="utf-8"))
        progress = state["cycle_progress"]
        assert progress["current_stage"] is None
        assert progress["model_pipeline"] == model_pipeline
        completed = {item["stage"]: item for item in progress["completed_stages"]}
        assert {"decision", "task_lifecycle", "daily_summary", "curator"} <= set(completed)
        assert all(item["duration_seconds"] >= 0 for item in completed.values())
        assert all(item["completed_at"] for item in completed.values())
        memory = json.loads(daemon.memory_index.index_file.read_text(encoding="utf-8"))
        latest = memory["entries"][-1]
        assert latest["type"] == "cycle_summary"
        assert latest["title"].startswith("运行周期摘要 - ")


def test_daemon_persists_heartbeat_model_and_backup_stage_progress():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {"runtime": {"backup_interval_seconds": 0}})
        daemon._run_shenwen_daily_health = lambda: {"executed": False}
        daemon.run_once = lambda **kwargs: {"auto_result": {"tasks_executed": 0}}
        daemon.run_periodic_backup = lambda: {"path": "backup"}

        daemon.run_daemon(interval_seconds=0, max_iterations=1, dry_run=True)

        state = json.loads(daemon.state_file.read_text(encoding="utf-8"))
        completed = {
            item["stage"]: item for item in state["cycle_progress"]["completed_stages"]
        }
        assert {"heartbeat", "model_health", "backup"} <= set(completed)
        assert all(item["duration_seconds"] >= 0 for item in completed.values())


def test_daemon_daily_learning_is_date_idempotent():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})

        first = daemon.run_daily_learning("2026-08-23")
        second = daemon.run_daily_learning("2026-08-23")

        assert first == second
        assert first["date"] == "2026-08-23"
        assert first["outcome"] in {
            "NO_VALID_LEARNING_TARGET",
            "LEARNING_CANDIDATE_DEFERRED",
            "observe",
            "reject",
            "adopt",
        }


def test_daemon_daily_learning_adapts_independent_data_health_evidence():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        health = {
            "available": True,
            "path": str(Path(temp_dir) / "benchmark.json"),
            "summary": {
                "sources": {
                    "source_a": {"availability": 0.4, "field_completeness": 1.0, "coverage": 0.5, "consistency": 0.8, "upstream_identity": "Upstream A", "independence_group": "group_a", "lineage_observable": True},
                    "source_b": {"availability": 0.5, "field_completeness": 0.7, "coverage": 1.0, "consistency": 0.6, "upstream_identity": "Upstream B", "independence_group": "group_b", "lineage_observable": True},
                }
            },
        }
        daemon.runtime_observer.record(
            description="Two independent data sources are degraded.",
            system_state={
                "stock_data_health": health,
                "degraded_sources": dict(health["summary"]["sources"]),
            },
            severity="high",
            source="stock_discovery",
            category="health",
            auto_generated=True,
        )
        for sequence in range(60):
            daemon.runtime_observer.record(
                description=f"Unrelated runtime observation {sequence}",
                system_state={"sequence": sequence},
                severity="low",
                source="daemon_loop",
                category="runtime",
                auto_generated=True,
            )

        candidates = daemon._daily_learning_candidates()

        assert len(candidates) == 1
        candidate, evidence = candidates[0]
        assert candidate.metadata["learning"]["required_evidence"]
        assert {item["source"] for item in evidence} == {"source_a", "source_b"}
        assert {item["metadata"]["independence_group"] for item in evidence} == {"group_a", "group_b"}
        assert {item["source_ref"] for item in evidence} == {
            f"{health['path']}#source_a",
            f"{health['path']}#source_b",
        }

        result = daemon.run_daily_learning("2026-08-24")
        assert result["outcome"] == "adopt"
        task = daemon.task_pool.load_task(result["task_id"])
        admission = task.outputs["admission"]
        assert admission["source_type"] == "learning"
        assert admission["source_ref"] == candidate.fingerprint
        assert admission["learning_contract"] == candidate.metadata["learning"]
        assert {item["source"] for item in admission["evidence"]} == {"source_a", "source_b"}


def test_scheduler_installer_defines_only_daemon_boot_task():
    powershell_source = (ROOT / "ops" / "install_tasks.ps1").read_text(encoding="utf-8")
    python_source = (ROOT / "ops" / "install_tasks.py").read_text(encoding="utf-8")

    assert 'Name = "ACE_Daemon_Boot"' in powershell_source
    assert "ACE_HealthCheck_Hourly" not in powershell_source
    assert "ACE_FullCheckup_Daily" not in powershell_source
    assert "daemon --serve" in powershell_source
    assert '"name": "ACE_Daemon_Boot"' in python_source
    assert "ACE_HealthCheck_Hourly" not in python_source
    assert "ACE_FullCheckup_Daily" not in python_source
    assert "daemon --serve" in python_source


def test_scheduler_installer_uses_valid_boot_delay_and_fails_on_registration_error():
    source = (ROOT / "ops" / "install_tasks.ps1").read_text(encoding="utf-8")

    assert 'Delay = "PT5M"' in source
    assert "-RepetitionInterval (New-TimeSpan -Minutes 10)" in source
    assert "-RepetitionDuration (New-TimeSpan -Days 1)" in source
    assert 'exit 1' in source[source.index('catch {'):]


def test_observation_signature_suppresses_persistent_duplicates_and_allows_recurrence():
    from core.observation import RuntimeObserver

    with tempfile.TemporaryDirectory() as temp_dir:
        observer = RuntimeObserver(temp_dir)
        first = observer.record(
            description="持续故障",
            system_state={"component": "telegram", "status": "missing"},
            source="resource_audit",
            category="health",
        )
        duplicate = observer.record(
            description="持续故障",
            system_state={"component": "telegram", "status": "missing"},
            source="resource_audit",
            category="health",
        )

        assert duplicate.obs_id == first.obs_id
        assert observer.get_stats()["total"] == 1

        observer.resolve_signature(first.signature)
        recurrence = observer.record(
            description="持续故障",
            system_state={"component": "telegram", "status": "missing"},
            source="resource_audit",
            category="health",
        )

        assert recurrence.obs_id != first.obs_id
        assert observer.get_stats()["total"] == 2


def test_backup_restores_required_runtime_assets_to_isolated_target():
    from ops.backup_data import backup_runtime, restore_backup

    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        required = [
            base_dir / "task_pool" / "pending",
            base_dir / "06_RUNTIME" / "ace" / "data" / "memory",
            base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "daily_learning",
            base_dir / "06_RUNTIME" / "ace" / "data" / "observations",
            base_dir / "09_KNOWLEDGE",
        ]
        for directory in required:
            directory.mkdir(parents=True, exist_ok=True)
        (base_dir / "task_pool" / "pending" / "task.json").write_text("{}", encoding="utf-8")
        (base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json").write_text("{}", encoding="utf-8")
        (base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "daily_learning" / "2026-08-23.json").write_text("{}", encoding="utf-8")
        (base_dir / "06_RUNTIME" / "ace" / "data" / "observations" / "observations.jsonl").write_text("", encoding="utf-8")
        (base_dir / "09_KNOWLEDGE" / "index.json").write_text("{}", encoding="utf-8")

        backup_dir, manifest = backup_runtime(base_dir)
        restored = base_dir / "isolated_restore"
        result = restore_backup(backup_dir, restored)

        assert manifest["version"] == 2
        assert {item["name"] for item in manifest["assets"]} >= {
            "task_pool", "memory", "daily_learning", "observations", "knowledge"
        }
        assert result["valid"] is True
        daily_learning = next(item for item in manifest["assets"] if item["name"] == "daily_learning")
        assert daily_learning["status"] == "backed_up"
        assert (restored / "task_pool" / "pending" / "task.json").exists()
        assert (restored / "06_RUNTIME" / "ace" / "data" / "memory" / "daily_learning" / "2026-08-23.json").exists()
        assert (restored / "09_KNOWLEDGE" / "index.json").exists()


def test_backup_manifest_records_missing_required_runtime_assets():
    from ops.backup_data import backup_runtime

    with tempfile.TemporaryDirectory() as temp_dir:
        backup_dir, manifest = backup_runtime(Path(temp_dir))

        daily_learning = next(
            item for item in manifest["assets"] if item["name"] == "daily_learning"
        )
        assert daily_learning["status"] == "missing"
        assert backup_dir.joinpath("manifest.json").exists()


def test_daemon_uses_fragment_status_breakdown_for_backlog_observation():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.fragment_index.get_stats = lambda: {
            "total": 501,
            "by_status": {"pending_scan": 501, "archaeologized": 4},
        }
        observations = []
        daemon.runtime_observer.record = lambda **kwargs: observations.append(kwargs)

        daemon._record_system_observations()

        fragment_observation = next(
            item for item in observations if item["description"].startswith("碎片索引积压")
        )
        assert fragment_observation["system_state"]["pending_scan"] == 501
        assert fragment_observation["system_state"]["archaeologized"] == 4


def test_daemon_records_periodic_backup_manifest():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {"runtime": {"backup_interval_seconds": 0}})
        result = daemon.run_periodic_backup()

        assert result["manifest"]["version"] == 2
        assert daemon.state["last_backup"]["path"] == result["path"]
        assert daemon.state_file.exists()


def test_daemon_state_save_keeps_last_complete_state_when_replace_is_interrupted(monkeypatch):
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.state = {"checkpoint": "previous"}
        daemon._save_state()
        daemon.state = {"checkpoint": "next"}

        def fail_replace(source, destination):
            raise OSError("interrupted replace")

        monkeypatch.setattr("ace_daemon.os.replace", fail_replace)
        with pytest.raises(OSError, match="interrupted replace"):
            daemon._save_state()

        assert json.loads(daemon.state_file.read_text(encoding="utf-8")) == {"checkpoint": "previous"}


def test_daemon_state_save_replaces_the_previous_complete_state():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.state = {"checkpoint": "previous"}
        daemon._save_state()
        daemon.state = {"checkpoint": "next"}
        daemon._save_state()

        assert json.loads(daemon.state_file.read_text(encoding="utf-8")) == {"checkpoint": "next"}


def test_daemon_state_load_recovers_a_complete_temporary_state_file():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        data_dir.mkdir(parents=True)
        state_file = data_dir / "daemon_state.json"
        state_file.write_text("{invalid", encoding="utf-8")
        temporary = data_dir / "daemon_state.json.recovery.tmp"
        temporary.write_text(json.dumps({"checkpoint": "recovered"}), encoding="utf-8")

        daemon = AceDaemon(Path(temp_dir), {})

        assert daemon.state == {"checkpoint": "recovered"}
        assert json.loads(state_file.read_text(encoding="utf-8")) == {"checkpoint": "recovered"}
        assert not temporary.exists()


def test_daemon_state_load_recovers_a_temporary_state_when_primary_is_missing():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        data_dir.mkdir(parents=True)
        temporary = data_dir / "daemon_state.json.recovery.tmp"
        temporary.write_text(json.dumps({"checkpoint": "recovered"}), encoding="utf-8")

        daemon = AceDaemon(Path(temp_dir), {})

        assert daemon.state == {"checkpoint": "recovered"}
        assert json.loads(daemon.state_file.read_text(encoding="utf-8")) == {"checkpoint": "recovered"}
        assert not temporary.exists()


def test_daemon_state_load_rejects_unrecoverable_corruption():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir) / "06_RUNTIME" / "ace" / "data" / "memory"
        data_dir.mkdir(parents=True)
        (data_dir / "daemon_state.json").write_text("{invalid", encoding="utf-8")

        with pytest.raises(RuntimeError, match="daemon_state.json"):
            AceDaemon(Path(temp_dir), {})


def test_scheduled_task_check_mode_parses():
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ROOT / "ops" / "install_tasks.ps1"),
            "-Check",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr or result.stdout


def test_lifecycle_model_pipeline_includes_same_cycle_persisted_execution_trace():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        task = daemon.task_pool.create_task(
            "Admitted reasoning task",
            priority="high",
            admission=model_task_admission(),
            tags=["task_type:reasoning"],
            outputs={"model_task_admission": {"eligible": True, "classification": "reasoning"}},
        )
        daemon.daily_learning = None
        daemon.mine_seed_scanner = None
        daemon.file_scanner = None
        daemon.event_listener = None
        daemon.observer = None
        daemon.discovery_mode = None
        daemon.obs_to_task_converter = None
        daemon.validator = None
        daemon.guardian = None
        daemon.archivist = None
        daemon.experience_deposition = None
        daemon.skill_generator = None
        daemon.task_creator = None

        class TraceWritingResearcher:
            def __init__(self):
                self.claimed = False

            def pick_up_task(self, priority):
                if self.claimed:
                    return None
                self.claimed = True
                return task

            def research_task(self, claimed_task):
                claimed_task.outputs["model_execution"] = [{
                    "provider": "provider-a",
                    "selected_model": "model-a",
                    "api_called": True,
                    "api_result": "success",
                    "fallback": False,
                    "trace_complete": True,
                }]
                daemon.task_pool.update_task(claimed_task)

        daemon.researcher = TraceWritingResearcher()

        result = daemon._run_task_lifecycle_unlocked()

        assert result["researched"] == 1
        assert result["model_pipeline"]["production_task_calls"] == 1
        assert result["model_pipeline"]["providers"] == {"provider-a": 1}


def test_model_pipeline_metrics_count_only_admitted_reasoning_execution_traces():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        admitted = daemon.task_pool.create_task(
            "Admitted reasoning task",
            priority="high",
            admission=model_task_admission(),
            tags=["task_type:reasoning"],
            outputs={
                "model_task_admission": {"eligible": True, "classification": "reasoning"},
                "model_execution": [{
                    "provider": "provider-a",
                    "selected_model": "model-a",
                    "api_called": True,
                    "api_result": "success",
                    "fallback": False,
                    "trace_complete": True,
                }],
            },
        )
        daemon.task_pool.create_task(
            "Health probe trace",
            priority="high",
            admission={**model_task_admission(), "source_ref": "health-probe"},
            tags=["task_type:strategic"],
            outputs={
                "model_execution": [{
                    "provider": "provider-b",
                    "api_called": True,
                    "api_result": "success",
                }],
            },
        )
        daemon.task_pool.create_task(
            "Rejected reasoning task",
            priority="high",
            admission={**model_task_admission(), "source_ref": "rejected-task"},
            tags=["task_type:reasoning"],
            outputs={
                "model_task_admission": {"eligible": False, "classification": "local_evidence_only"},
                "model_execution": [{
                    "provider": "provider-c",
                    "api_called": True,
                    "api_result": "success",
                }],
            },
        )

        metrics = daemon._model_pipeline_metrics()

        assert admitted.task_id
        assert metrics["reasoning_tasks_created"] == 1
        assert metrics["production_task_calls"] == 1
        assert metrics["providers"] == {"provider-a": 1}
        assert metrics["selected_models"] == {"model-a": 1}
        assert metrics["api_called"] == 1
        assert metrics["api_result"] == {"success": 1}
        assert metrics["fallback"] == {"false": 1}
        assert metrics["trace_complete"] == 1


def test_model_pipeline_metrics_are_read_only():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.miner_pool.chat = lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not call provider"))
        daemon.task_pool.create_task(
            "Admitted reasoning task",
            priority="high",
            admission=model_task_admission(),
            tags=["task_type:reasoning"],
            outputs={"model_task_admission": {"eligible": True, "classification": "reasoning"}},
        )

        metrics = daemon._model_pipeline_metrics()

        assert metrics["production_task_calls"] == 0


def test_cycle_terminal_checkpoint_refreshes_daily_shift_from_final_state():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        observed = []

        class CapturingDailyShift:
            def build(self, *, daemon_state_path):
                state = json.loads(Path(daemon_state_path).read_text(encoding="utf-8"))
                observed.append({
                    "cycle_status": state["cycle_progress"]["cycle_status"],
                    "stop_reason": state["cycle_progress"]["stop_reason"],
                })
                return observed[-1]

        daemon.daily_shift = CapturingDailyShift()
        daemon.state["cycle_progress"] = {
            "current_stage": "repository_sync",
            "completed_stages": [],
        }

        daemon._finalize_cycle("completed", "cycle_complete")

        assert observed == [{
            "cycle_status": "completed",
            "stop_reason": "cycle_complete",
        }]


if __name__ == "__main__":
    test_daemon_import_and_construction()
    test_daemon_service_entrypoint()
    test_daemon_process_lock_excludes_second_daemon()
    test_daemon_lock_releases_when_startup_raises()
    test_atomic_task_claim_preserves_valid_lease_and_recovers_stale_lease()
    test_stale_lock_file_does_not_block_task_claim()
    test_retry_backoff_prevents_early_reclaim()
    test_recovery_keeps_latest_duplicate_task_state()
    test_researchers_use_atomic_task_claims()
    test_daemon_reclaims_stale_leases_before_work()
    test_researcher_failure_is_persisted_for_retry()
    test_stale_claim_cannot_overwrite_new_owner()
    test_external_blocks_do_not_auto_release()
    test_archivist_preserves_task_fencing_on_archive()
    test_archivist_requires_guardian_archive_decision()
    test_repeated_review_does_not_force_approval_without_passing_validation()
    test_self_healing_checks_current_task_pool_directory()
    test_self_healing_recovers_current_task_pool_through_state_machine()
    test_legacy_archive_scripts_cannot_bypass_guardian_and_archivist()
    test_backup_covers_complete_task_pool_and_cleanup_preserves_records()
    test_daemon_daily_learning_is_date_idempotent()
    test_daemon_daily_learning_adapts_independent_data_health_evidence()
    test_only_daemon_scheduled_task_is_unlimited()
    test_scheduled_task_check_mode_parses()
    print("24h runtime mainline startup tests passed")
