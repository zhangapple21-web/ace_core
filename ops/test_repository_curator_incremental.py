import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from core.repository_curator import RepositoryCurator


def _curator(root: Path) -> RepositoryCurator:
    return RepositoryCurator(
        ace_runtime_dir=str(root / "runtime"),
        mine_seed_dir=str(root / "mine-seed"),
        ace_core_dir=str(root / "ace-core"),
        data_dir=str(root / "curator-data"),
    )


def _set_mtime(path: Path, value: datetime) -> None:
    timestamp = value.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_curator_restart_uses_persisted_cursor_and_only_collects_new_artifacts():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifacts = root / "runtime" / "09_KNOWLEDGE"
        artifacts.mkdir(parents=True)
        old = artifacts / "old.md"
        new = artifacts / "new.md"
        old.write_text("# old\nold knowledge", encoding="utf-8")
        new.write_text("# new\nnew knowledge", encoding="utf-8")
        cursor = datetime.now() - timedelta(minutes=5)
        _set_mtime(old, cursor - timedelta(minutes=1))
        _set_mtime(new, cursor + timedelta(minutes=1))

        data_dir = root / "curator-data"
        data_dir.mkdir()
        (data_dir / "curation_history.json").write_text(
            json.dumps([{"timestamp": cursor.isoformat(), "status": "completed"}]),
            encoding="utf-8",
        )

        curator = _curator(root)
        curator._scan_target_repos = lambda: []
        result = curator.wakeup(triggered_by="daemon_loop")

        assert result["status"] == "completed"
        assert result["artifacts_scanned"] == 1
        assert result["decisions"][0]["title"] == "new"
        assert result["cursor_from"] == cursor.isoformat()
        assert result["cursor_to"]


def test_curator_empty_increment_does_not_scan_target_repositories():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifacts = root / "runtime" / "08_ARCHAEOLOGY"
        artifacts.mkdir(parents=True)
        old = artifacts / "old.md"
        old.write_text("# old\nalready curated", encoding="utf-8")
        cursor = datetime.now() - timedelta(minutes=1)
        _set_mtime(old, cursor - timedelta(minutes=1))

        data_dir = root / "curator-data"
        data_dir.mkdir()
        (data_dir / "curation_history.json").write_text(
            json.dumps([{"cursor_to": cursor.isoformat(), "status": "completed"}]),
            encoding="utf-8",
        )
        curator = _curator(root)

        def forbidden_scan():
            raise AssertionError("target repositories must not be scanned without new artifacts")

        curator._scan_target_repos = forbidden_scan
        result = curator.wakeup(triggered_by="daemon_loop")

        assert result["status"] == "completed"
        assert result["artifacts_scanned"] == 0
        assert result["decisions"] == []
        assert result["summary"] == "无新增产物"


def test_curator_cursor_uses_scan_start_so_changes_during_run_are_not_lost():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        artifacts = root / "runtime" / "04_PROTOCOLS"
        artifacts.mkdir(parents=True)
        first = artifacts / "first.md"
        first.write_text("# first\nfirst version", encoding="utf-8")
        _set_mtime(first, datetime.now() - timedelta(minutes=1))
        curator = _curator(root)
        curator._scan_target_repos = lambda: []

        initial = curator.wakeup(triggered_by="daemon_loop")
        cursor_to = datetime.fromisoformat(initial["cursor_to"])
        changed_during_run = artifacts / "during.md"
        changed_during_run.write_text("# during\ncreated after scan began", encoding="utf-8")
        _set_mtime(changed_during_run, cursor_to + timedelta(microseconds=1))

        restarted = _curator(root)
        restarted._scan_target_repos = lambda: []
        followup = restarted.wakeup(triggered_by="daemon_loop")

        assert followup["artifacts_scanned"] == 1
        assert followup["decisions"][0]["title"] == "during"


def test_curator_never_reprocesses_its_own_runtime_heartbeats_as_knowledge():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        runtime = root / "runtime"
        volatile = runtime / "06_RUNTIME" / "ace" / "data" / "memory"
        durable = runtime / "docs"
        volatile.mkdir(parents=True)
        durable.mkdir(parents=True)
        (volatile / "heartbeat.json").write_text('{"status": "alive"}', encoding="utf-8")
        (volatile / "daemon_state.json").write_text('{"run": "current"}', encoding="utf-8")
        (durable / "decision.md").write_text("# Durable decision\n", encoding="utf-8")

        curator = _curator(root)
        artifacts = curator._collect_today_artifacts()

        assert [Path(item["path"]).name for item in artifacts] == ["decision.md"]
