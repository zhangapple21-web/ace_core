"""Read-only Trae/Codex host-session metadata observer.

ACE already has RuntimeObserver and Environment Awareness, but neither looked
at the two hosts the operator actually uses.  This module fills that gap with
minimized, already-on-disk metadata:

- Codex: ``local_thread_catalog`` (title / cwd / mtime) or ``session_index.jsonl``
- Trae: workspace folder + last session id from VS Code ItemTable allowlist

It is perception, not a control plane.  It never reads conversation bodies,
never claims ``active_work_manifest``, never creates TaskPool work, and never
treats a session title as user intent.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse


CONTRACT_VERSION = "ace.host_session.v1"
SOURCE = "host_session"
CATEGORY = "environment_change"
PERCEPTION_ONLY_TOKEN = "PERCEPTION_ONLY"
_TITLE_LIMIT = 80
_SESSION_LIMIT = 8

_TRAE_ALLOWED_KEYS = (
    "ai-chat-v2.lastActiveSessionId",
    "icube_session_agent_map",
)

FORBIDDEN_ACTIONS = (
    "automatic_task_creation",
    "conversation_body_read",
    "desktop_surveillance",
    "manifest_claim",
    "model_call",
    "intent_inference",
)


def default_codex_home() -> Path:
    return Path.home() / ".codex"


def default_trae_roaming() -> Path:
    return Path.home() / "AppData" / "Roaming" / "Trae"


def _utc_now(value: datetime | None = None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clip_title(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text[:_TITLE_LIMIT]


def _unix_to_iso(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    try:
        ts = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    if ts > 10_000_000_000:
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _uri_to_path(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("file:"):
        parsed = urlparse(value)
        path = unquote(parsed.path or "")
        if path.startswith("/") and len(path) >= 3 and path[2] == ":":
            path = path[1:]
        return path.replace("/", "\\") if path else None
    return value


def _open_sqlite_ro(path: Path) -> Optional[sqlite3.Connection]:
    if not path.is_file():
        return None
    uri = f"file:{path.as_posix()}?mode=ro"
    try:
        return sqlite3.connect(uri, uri=True, timeout=0.2)
    except sqlite3.Error:
        return None


def collect_codex_sessions(
    codex_home: str | Path | None = None,
    *,
    limit: int = _SESSION_LIMIT,
) -> Dict[str, Any]:
    """Collect Codex thread metadata.  Never opens rollout jsonl bodies."""
    home = Path(codex_home) if codex_home is not None else default_codex_home()
    result: Dict[str, Any] = {
        "host": "codex",
        "available": False,
        "source_ref": None,
        "recent": [],
    }
    if not home.exists():
        return result

    catalog = _collect_codex_catalog(home / "sqlite" / "codex-dev.db", limit)
    if catalog:
        result["available"] = True
        result["source_ref"] = "codex.local_thread_catalog.v1"
        result["recent"] = catalog
        return result

    index_rows = _collect_codex_session_index(home / "session_index.jsonl", limit)
    if index_rows:
        result["available"] = True
        result["source_ref"] = "codex.session_index.v1"
        result["recent"] = index_rows
        return result

    result["available"] = True
    result["source_ref"] = "codex.home_present_no_sessions"
    return result


def _collect_codex_catalog(db_path: Path, limit: int) -> List[Dict[str, Any]]:
    con = _open_sqlite_ro(db_path)
    if con is None:
        return []
    rows: List[Dict[str, Any]] = []
    try:
        cur = con.cursor()
        cur.execute(
            """
            SELECT thread_id, display_title, cwd, git_branch, source_kind,
                   source_updated_at, source_recency_at, host_id
            FROM local_thread_catalog
            WHERE host_id = 'local'
            ORDER BY COALESCE(source_recency_at, source_updated_at) DESC
            LIMIT ?
            """,
            (int(limit),),
        )
        for row in cur.fetchall():
            session_id, title, cwd, branch, kind, updated, recency, host_id = row
            rows.append(
                {
                    "host": "codex",
                    "session_id": str(session_id) if session_id else None,
                    "title": _clip_title(title),
                    "cwd": str(cwd) if cwd else None,
                    "git_branch": str(branch) if branch else None,
                    "source_kind": str(kind) if kind else None,
                    "updated_at": _unix_to_iso(recency or updated),
                    "title_epistemic": "FACT" if title else "UNKNOWN",
                    "host_id": str(host_id) if host_id else "local",
                }
            )
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return rows


def _collect_codex_session_index(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    parsed: List[Dict[str, Any]] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        parsed.append(
            {
                "host": "codex",
                "session_id": str(rec["id"]) if rec.get("id") else None,
                "title": _clip_title(rec.get("thread_name") or rec.get("title")),
                "cwd": None,
                "git_branch": None,
                "source_kind": "session_index",
                "updated_at": str(rec["updated_at"]) if rec.get("updated_at") else None,
                "title_epistemic": "FACT" if rec.get("thread_name") or rec.get("title") else "UNKNOWN",
                "host_id": "local",
            }
        )
        if len(parsed) >= limit:
            break
    return parsed


def collect_trae_sessions(
    trae_roaming: str | Path | None = None,
    *,
    limit: int = _SESSION_LIMIT,
) -> Dict[str, Any]:
    """Collect Trae workspace / session ids.  Titles are UNKNOWN unless stored separately.

    Allowed ItemTable keys only.  Chat drafts, input history and conversation
    bodies are not read.
    """
    root = Path(trae_roaming) if trae_roaming is not None else default_trae_roaming()
    result: Dict[str, Any] = {
        "host": "trae",
        "available": False,
        "source_ref": None,
        "workspace": None,
        "last_session_id": None,
        "session_ids": [],
        "title": None,
        "title_epistemic": "UNKNOWN",
        "updated_at": None,
        "recent": [],
    }
    if not root.exists():
        return result

    result["available"] = True
    result["source_ref"] = "trae.workspace_identity.v1"
    workspace, updated_at = _trae_workspace(root)
    result["workspace"] = workspace
    result["updated_at"] = updated_at

    last_id, session_ids = _trae_session_ids(root, limit)
    result["last_session_id"] = last_id
    result["session_ids"] = session_ids
    if last_id or workspace:
        result["recent"] = [
            {
                "host": "trae",
                "session_id": last_id,
                "title": None,
                "cwd": workspace,
                "git_branch": None,
                "source_kind": "workspace_storage",
                "updated_at": updated_at,
                "title_epistemic": "UNKNOWN",
                "host_id": "local",
            }
        ]
    return result


def _trae_workspace(root: Path) -> tuple[Optional[str], Optional[str]]:
    storage = root / "User" / "globalStorage" / "storage.json"
    workspace_dir = root / "User" / "workspaceStorage"
    folder = None
    mtime = None
    if storage.is_file():
        try:
            data = json.loads(storage.read_text(encoding="utf-8"))
            window = (data.get("windowsState") or {}).get("lastActiveWindow") or {}
            folder = _uri_to_path(window.get("folder"))
            mtime = datetime.fromtimestamp(storage.stat().st_mtime, tz=timezone.utc).isoformat()
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    if workspace_dir.is_dir():
        newest = None
        for child in workspace_dir.iterdir():
            marker = child / "workspace.json"
            if not marker.is_file():
                continue
            if newest is None or marker.stat().st_mtime > newest.stat().st_mtime:
                newest = marker
        if newest is not None:
            try:
                payload = json.loads(newest.read_text(encoding="utf-8"))
                folder = _uri_to_path(payload.get("folder")) or folder
                mtime = datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc).isoformat()
            except (OSError, json.JSONDecodeError, TypeError):
                pass
    return folder, mtime


def _trae_session_ids(root: Path, limit: int) -> tuple[Optional[str], List[str]]:
    last_id = None
    session_ids: List[str] = []
    seen = set()
    paths = [
        root / "User" / "workspaceStorage",
        root / "User" / "globalStorage" / "state.vscdb",
    ]
    workspace_dir = paths[0]
    db_files: List[Path] = []
    if workspace_dir.is_dir():
        for child in workspace_dir.iterdir():
            candidate = child / "state.vscdb"
            if candidate.is_file():
                db_files.append(candidate)
    if paths[1].is_file():
        db_files.append(paths[1])

    for db_path in db_files:
        values = _read_itemtable_allowlist(db_path)
        if not last_id:
            last_id = values.get("ai-chat-v2.lastActiveSessionId")
            if isinstance(last_id, str):
                last_id = last_id.strip() or None
            else:
                last_id = None
        mapping = values.get("icube_session_agent_map")
        if isinstance(mapping, dict):
            for key in mapping:
                if not isinstance(key, str) or key.startswith("__") or key in seen:
                    continue
                seen.add(key)
                session_ids.append(key)
                if len(session_ids) >= limit:
                    break
        if last_id and len(session_ids) >= limit:
            break
    if last_id and last_id not in seen:
        session_ids.insert(0, last_id)
    return last_id, session_ids[:limit]


def _read_itemtable_allowlist(db_path: Path) -> Dict[str, Any]:
    con = _open_sqlite_ro(db_path)
    if con is None:
        return {}
    out: Dict[str, Any] = {}
    try:
        cur = con.cursor()
        placeholders = ",".join("?" * len(_TRAE_ALLOWED_KEYS))
        cur.execute(
            f"SELECT key, value FROM ItemTable WHERE key IN ({placeholders})",
            _TRAE_ALLOWED_KEYS,
        )
        for key, value in cur.fetchall():
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            if not isinstance(value, str):
                continue
            text = value.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    out[key] = json.loads(text)
                    continue
                except json.JSONDecodeError:
                    pass
            out[key] = text
    except sqlite3.Error:
        return {}
    finally:
        con.close()
    return out


def overlay_manifest(manifest_path: str | Path | None) -> Optional[Dict[str, Any]]:
    """Read-only view of agent_team manifest.  Never claims or renews entries."""
    if manifest_path is None:
        return None
    path = Path(manifest_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return {"available": False}
    slim = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        slim.append(
            {
                "work_id": entry.get("work_id"),
                "owner": entry.get("owner"),
                "status": entry.get("status"),
                "workspace": entry.get("workspace"),
                "heartbeat_at": entry.get("heartbeat_at"),
            }
        )
    return {
        "available": True,
        "source_ref": "agent_team.active_work_manifest.v2",
        "read_only": True,
        "entries": slim,
    }


def build_snapshot(
    *,
    codex: Dict[str, Any],
    trae: Dict[str, Any],
    manifest: Optional[Dict[str, Any]] = None,
    observed_at: datetime | None = None,
) -> Dict[str, Any]:
    observed = _utc_now(observed_at)
    return {
        "contract_version": CONTRACT_VERSION,
        "observed_at": observed.isoformat(),
        "production_integration": False,
        "taskpool_task_created": False,
        "taskpool_authority": False,
        "raw_retention": "NONE",
        "conversation_bodies_read": False,
        "intent_inferred": False,
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "hosts": {"codex": codex, "trae": trae},
        "collaboration_manifest": manifest or {"available": False, "read_only": True},
    }


def snapshot_path_for(base_dir: str | Path) -> Path:
    return Path(base_dir) / "06_RUNTIME" / "ace" / "data" / "host_sessions_latest.json"


def persist_snapshot(path: str | Path, snapshot: Dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return target


def _latest_identity(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    hosts = snapshot.get("hosts") or {}
    codex_recent = (hosts.get("codex") or {}).get("recent") or []
    trae = hosts.get("trae") or {}
    return {
        "codex": [
            {
                "session_id": item.get("session_id"),
                "updated_at": item.get("updated_at"),
            }
            for item in codex_recent[:3]
            if isinstance(item, dict)
        ],
        "trae_workspace": trae.get("workspace"),
        "trae_last_session_id": trae.get("last_session_id"),
    }


def describe_snapshot(snapshot: Dict[str, Any]) -> str:
    hosts = snapshot.get("hosts") or {}
    codex = hosts.get("codex") or {}
    trae = hosts.get("trae") or {}
    recent = codex.get("recent") or []
    latest = recent[0] if recent else {}
    title = latest.get("title") or "UNKNOWN"
    cwd = latest.get("cwd") or "UNKNOWN"
    trae_ws = trae.get("workspace") or "UNKNOWN"
    trae_sid = trae.get("last_session_id") or "UNKNOWN"
    return (
        f"FACT: Codex 最近会话「{title}」(cwd={cwd}); "
        f"Trae 工作区={trae_ws}, last_session_id={trae_sid}。"
        "标题不是意图，不自动建任务。"
    )


def record_snapshot(observer: Any, snapshot: Dict[str, Any]) -> Any:
    if observer is None:
        return None
    return observer.record(
        description=describe_snapshot(snapshot),
        system_state={
            "contract_version": CONTRACT_VERSION,
            "hosts": snapshot.get("hosts"),
            "collaboration_manifest": snapshot.get("collaboration_manifest"),
            "conversation_bodies_read": False,
            "intent_inferred": False,
            "taskpool_task_created": False,
        },
        severity="low",
        source=SOURCE,
        category=CATEGORY,
        auto_generated=True,
        dedup_key=_latest_identity(snapshot),
    )


def observe_host_sessions(
    *,
    observer: Any = None,
    base_dir: str | Path | None = None,
    codex_home: str | Path | None = None,
    trae_roaming: str | Path | None = None,
    manifest_path: str | Path | None = None,
    observed_at: datetime | None = None,
) -> Dict[str, Any]:
    """Collect, persist, and optionally record.  Never creates TaskPool work."""
    snapshot = build_snapshot(
        codex=collect_codex_sessions(codex_home),
        trae=collect_trae_sessions(trae_roaming),
        manifest=overlay_manifest(manifest_path),
        observed_at=observed_at,
    )
    if base_dir is not None:
        persist_snapshot(snapshot_path_for(base_dir), snapshot)
    observation = record_snapshot(observer, snapshot)
    snapshot["observation_id"] = getattr(observation, "obs_id", None)
    return snapshot
