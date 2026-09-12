"""Host-session perception: metadata only, never Work, never conversation bodies."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.host_session_observer import (
    collect_codex_sessions,
    collect_trae_sessions,
    observe_host_sessions,
)
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.task import TaskPool


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
SECRET = "SECRET_CONVERSATION_BODY_MUST_NOT_LEAK"


def _write_codex_catalog(home: Path, title: str, cwd: str, thread_id: str = "thread-1") -> None:
    db_dir = home / "sqlite"
    db_dir.mkdir(parents=True)
    db = db_dir / "codex-dev.db"
    con = sqlite3.connect(db)
    con.execute(
        """
        CREATE TABLE local_thread_catalog (
            host_id TEXT,
            thread_id TEXT,
            display_title TEXT,
            source_created_at REAL,
            source_updated_at REAL,
            cwd TEXT,
            source_kind TEXT,
            source_detail TEXT,
            model_provider TEXT,
            git_branch TEXT,
            observation_sequence INTEGER,
            missing_candidate INTEGER,
            thread_source TEXT,
            source_recency_at REAL,
            pending_observed_title TEXT,
            project_id TEXT,
            conversation_origin TEXT
        )
        """
    )
    con.execute(
        """
        INSERT INTO local_thread_catalog (
            host_id, thread_id, display_title, cwd, git_branch, source_kind,
            source_updated_at, source_recency_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("local", thread_id, title, cwd, "main", "vscode", 1789124626.0, 1789124626.0),
    )
    con.commit()
    con.close()
    rollout = home / "sessions" / "2026" / "09" / "11"
    rollout.mkdir(parents=True)
    (rollout / f"rollout-{thread_id}.jsonl").write_text(
        json.dumps({"type": "user_message", "text": SECRET}),
        encoding="utf-8",
    )


def _write_codex_index(home: Path, title: str, thread_id: str = "thread-index") -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "session_index.jsonl").write_text(
        json.dumps(
            {
                "id": thread_id,
                "thread_name": title,
                "updated_at": "2026-09-11T11:03:47Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_trae(root: Path, workspace_uri: str, session_id: str) -> None:
    ws = root / "User" / "workspaceStorage" / "abc123"
    gs = root / "User" / "globalStorage"
    ws.mkdir(parents=True)
    gs.mkdir(parents=True)
    (ws / "workspace.json").write_text(
        json.dumps({"folder": workspace_uri}),
        encoding="utf-8",
    )
    (gs / "storage.json").write_text(
        json.dumps({"windowsState": {"lastActiveWindow": {"folder": workspace_uri}}}),
        encoding="utf-8",
    )
    db = ws / "state.vscdb"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    con.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("ai-chat-v2.lastActiveSessionId", session_id),
    )
    con.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("icube_session_agent_map", json.dumps({session_id: "solo_agent"})),
    )
    con.execute(
        "INSERT INTO ItemTable VALUES (?, ?)",
        ("icube-ai-agent-storage-input-history", SECRET),
    )
    con.commit()
    con.close()


def test_codex_catalog_is_metadata_only(tmp_path):
    home = tmp_path / "codex"
    _write_codex_catalog(home, "核对远程 Git 与 ACE 当前实现", r"C:\tmp\ace_core")

    result = collect_codex_sessions(home)

    assert result["available"] is True
    assert result["source_ref"] == "codex.local_thread_catalog.v1"
    latest = result["recent"][0]
    assert latest["title"] == "核对远程 Git 与 ACE 当前实现"
    assert latest["cwd"] == r"C:\tmp\ace_core"
    assert latest["title_epistemic"] == "FACT"
    blob = json.dumps(result, ensure_ascii=False)
    assert SECRET not in blob


def test_codex_falls_back_to_session_index(tmp_path):
    home = tmp_path / "codex"
    _write_codex_index(home, "独立检查 ACE 刷机后完整性")

    result = collect_codex_sessions(home)

    assert result["source_ref"] == "codex.session_index.v1"
    assert result["recent"][0]["title"] == "独立检查 ACE 刷机后完整性"


def test_trae_reads_workspace_and_session_id_not_history(tmp_path):
    root = tmp_path / "Trae"
    _write_trae(
        root,
        "file:///d%3A/tmp/ACE_SYSTEM_BACKUP_20260908_200634/01",
        "sess-abc",
    )

    result = collect_trae_sessions(root)

    assert result["available"] is True
    assert result["last_session_id"] == "sess-abc"
    assert result["workspace"].replace("/", "\\").lower().endswith(
        r"\tmp\ace_system_backup_20260908_200634\01"
    )
    assert result["title"] is None
    assert result["title_epistemic"] == "UNKNOWN"
    blob = json.dumps(result, ensure_ascii=False)
    assert SECRET not in blob


def test_observe_persists_snapshot_and_does_not_create_tasks(tmp_path):
    base = tmp_path / "ace_core"
    obs_dir = base / "obs"
    pool_dir = base / "pool"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "entries": [
                    {
                        "work_id": "w1",
                        "owner": "codex-window-root",
                        "status": "completed",
                        "workspace": r"C:\tmp\ace_core",
                        "heartbeat_at": "2026-08-27T11:37:00+00:00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    codex = tmp_path / "codex"
    _write_codex_catalog(codex, "排查推票问题根因", r"C:\tmp")
    trae = tmp_path / "Trae"
    _write_trae(trae, "file:///C:/tmp/ace_core", "sess-1")

    observer = RuntimeObserver(str(obs_dir))
    pool = TaskPool(str(pool_dir))
    snapshot = observe_host_sessions(
        observer=observer,
        base_dir=base,
        codex_home=codex,
        trae_roaming=trae,
        manifest_path=manifest,
        observed_at=NOW,
    )
    converter = ObservationToTaskConverter(observer, pool)
    converted = converter.convert()

    snap_file = base / "06_RUNTIME" / "ace" / "data" / "host_sessions_latest.json"
    assert snap_file.is_file()
    stored = json.loads(snap_file.read_text(encoding="utf-8"))
    assert stored["contract_version"] == "ace.host_session.v1"
    assert stored["production_integration"] is False
    assert stored["taskpool_task_created"] is False
    assert stored["conversation_bodies_read"] is False
    assert stored["intent_inferred"] is False
    assert stored["hosts"]["codex"]["recent"][0]["title"] == "排查推票问题根因"
    assert stored["collaboration_manifest"]["read_only"] is True
    assert SECRET not in snap_file.read_text(encoding="utf-8")

    assert snapshot["observation_id"]
    assert converted["tasks_created"] == 0
    assert pool.get_stats().get("total", 0) == 0
    recorded = observer.get_recent(limit=1)[0]
    assert recorded.source == "host_session"
    assert recorded.category == "environment_change"
    assert recorded.task_generated == "PERCEPTION_ONLY"


if __name__ == "__main__":
    import tempfile

    tests = [
        test_codex_catalog_is_metadata_only,
        test_codex_falls_back_to_session_index,
        test_trae_reads_workspace_and_session_id_not_history,
        test_observe_persists_snapshot_and_does_not_create_tasks,
    ]
    failed = 0
    for fn in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                print("PASS", fn.__name__)
            except Exception as exc:
                failed += 1
                print("FAIL", fn.__name__, type(exc).__name__, exc)
    raise SystemExit(failed)
