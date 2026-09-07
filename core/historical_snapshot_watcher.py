"""Research-only watcher for newly dropped historical market snapshots.

The watcher scans a caller-selected data directory, hashes files, and invokes
the existing historical replay only for snapshots that carry the required
metadata.  It never fetches data, modifies the runtime, or creates production
records.  State and reports belong to the free-research sandbox.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .historical_factor_replay import load_snapshot, replay_momentum


CONTRACT_VERSION = "ace.historical_snapshot_watcher.v1"
SUPPORTED_EXTENSIONS = frozenset({".json", ".csv", ".parquet"})
EXCLUDED_DIRECTORY_NAMES = frozenset({"backups", "memory", "public_sentiment_evidence", "reports"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".metadata.json")


def _load_metadata(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    sidecar = _sidecar(path)
    if not sidecar.exists():
        return None, "metadata_sidecar_missing"
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, "metadata_sidecar_invalid"
    if not isinstance(value, Mapping):
        return None, "metadata_sidecar_not_mapping"
    return dict(value), None


def _rows_from_tabular(path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    if path.suffix.lower() == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, UnicodeDecodeError, csv.Error):
            return None, "tabular_read_failed"
        return rows, None if rows else "tabular_rows_empty"
    try:
        import pandas as pd  # type: ignore

        frame = pd.read_parquet(path)
        return frame.to_dict(orient="records"), None if len(frame.index) else "tabular_rows_empty"
    except ImportError:
        return None, "parquet_reader_unavailable"
    except Exception as exc:  # pragma: no cover - engine-specific errors
        return None, f"parquet_read_failed:{type(exc).__name__}"


def _tabular_snapshot(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    file_hash = _sha256(path)
    metadata, error = _load_metadata(path)
    if metadata is None:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": error, "path": str(path), "file_hash": file_hash}
    rows, error = _rows_from_tabular(path)
    if rows is None:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": error, "path": str(path), "file_hash": file_hash}
    # Reuse the JSON validator without writing an intermediate file.  The
    # replay module's public row checks are intentionally represented here for
    # tabular inputs so the watcher remains read-only.
    source_refs = metadata.get("source_refs")
    split = metadata.get("out_of_sample_split")
    if not isinstance(source_refs, list) or not source_refs:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "source_refs_missing", "path": str(path), "file_hash": file_hash}
    if metadata.get("lineage_observable") is not True:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "lineage_not_observable", "path": str(path), "file_hash": file_hash}
    if not isinstance(metadata.get("point_in_time_rule"), str) or not metadata["point_in_time_rule"].strip():
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "point_in_time_rule_missing", "path": str(path), "file_hash": file_hash}
    if not isinstance(split, Mapping) or any(not isinstance(split.get(key), str) or not split[key].strip() for key in ("train", "validation", "test")):
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "out_of_sample_split_missing_or_incomplete", "path": str(path), "file_hash": file_hash}
    if not isinstance(metadata.get("cost_model"), Mapping) or not metadata["cost_model"]:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "cost_model_missing", "path": str(path), "file_hash": file_hash}
    if metadata.get("cross_source_consistency") is not True:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "cross_source_consistency_not_confirmed", "path": str(path), "file_hash": file_hash}
    required = ("timestamp", "symbol", "open", "high", "low", "close", "volume")
    normalized = []
    seen: set[tuple[str, str]] = set()
    try:
        for index, row in enumerate(rows):
            if not isinstance(row, Mapping) or any(field not in row for field in required):
                raise ValueError(f"row_{index}_missing_required_field")
            timestamp, symbol = str(row["timestamp"]).strip(), str(row["symbol"]).strip()
            if not timestamp or not symbol:
                raise ValueError(f"row_{index}_identity_missing")
            if (timestamp, symbol) in seen:
                raise ValueError(f"duplicate_row:{timestamp}:{symbol}")
            seen.add((timestamp, symbol))
            item = {"timestamp": timestamp, "symbol": symbol}
            for field in ("open", "high", "low", "close", "volume"):
                item[field] = float(row[field])
                if not math_is_finite(item[field], field) or (field == "close" and item[field] <= 0) or (field == "volume" and item[field] < 0):
                    raise ValueError(f"row_{index}_invalid_{field}")
            if item["high"] < max(item["open"], item["close"]) or item["low"] > min(item["open"], item["close"]) or item["low"] > item["high"]:
                raise ValueError(f"row_{index}_ohlc_relationship_invalid")
            normalized.append(item)
    except (TypeError, ValueError) as exc:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": str(exc), "path": str(path), "file_hash": file_hash}
    sessions = sorted({row["timestamp"] for row in normalized})
    symbols = sorted({row["symbol"] for row in normalized})
    if len(sessions) < 20:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "fewer_than_20_sessions", "sessions": len(sessions), "symbols": len(symbols), "path": str(path), "file_hash": file_hash}
    if len(symbols) < 3:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "fewer_than_3_symbols", "sessions": len(sessions), "symbols": len(symbols), "path": str(path), "file_hash": file_hash}
    return {"metadata": {**metadata, "file_hash": file_hash, "sessions": sessions, "symbols": symbols}, "rows": normalized}, {"status": "ELIGIBLE", "sessions": len(sessions), "symbols": len(symbols), "file_hash": file_hash}


def math_is_finite(value: float, field: str) -> bool:
    import math

    return math.isfinite(value)


def _discover(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    paths = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or path.name.endswith(".metadata.json"):
            continue
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in path.relative_to(root).parts[:-1]):
            continue
        if ".tmp" in path.name:
            continue
        paths.append(path)
    return sorted(paths)


def watch_once(root: str | Path, state_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    root, state_path, report_path = Path(root), Path(state_path), Path(report_path)
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        state = {}
    seen = state.get("files", {}) if isinstance(state, Mapping) and isinstance(state.get("files"), Mapping) else {}
    content_index = state.get("content_hashes", {}) if isinstance(state, Mapping) and isinstance(state.get("content_hashes"), Mapping) else {}
    files = {}
    content_hashes = dict(content_index)
    entries = []
    for path in _discover(root):
        file_hash = _sha256(path)
        key = str(path.resolve())
        previous = seen.get(key)
        if isinstance(previous, Mapping) and previous.get("file_hash") == file_hash:
            entries.append({"path": key, "file_hash": file_hash, "status": "UNCHANGED", "replay_invoked": False})
            files[key] = dict(previous)
            continue
        canonical_path = content_hashes.get(file_hash)
        if isinstance(canonical_path, str) and canonical_path != key:
            entries.append({"path": key, "file_hash": file_hash, "status": "DUPLICATE_CONTENT", "canonical_path": canonical_path, "replay_invoked": False})
            files[key] = {"file_hash": file_hash, "last_status": "DUPLICATE_CONTENT", "replay_invoked": False, "canonical_path": canonical_path}
            continue
        if path.suffix.lower() == ".json":
            snapshot, result = load_snapshot(path)
        else:
            snapshot, result = _tabular_snapshot(path)
        replay_invoked = False
        if snapshot is not None:
            result = replay_momentum(snapshot)
            replay_invoked = True
        result = {**result, "path": key, "file_hash": file_hash, "extension": path.suffix.lower(), "replay_invoked": replay_invoked}
        entries.append(result)
        files[key] = {"file_hash": file_hash, "last_status": result.get("status"), "replay_invoked": replay_invoked}
        content_hashes[file_hash] = key
    report = {
        "contract_version": CONTRACT_VERSION,
        "mode": "FACTOR_RESEARCH_ONLY",
        "watch_root": str(root.resolve()),
        "scanned_count": len(files),
        "new_or_changed_count": sum(item.get("status") != "UNCHANGED" for item in entries),
        "replay_invoked_count": sum(bool(item.get("replay_invoked")) for item in entries),
        "entries": entries,
        "production_integration": False,
        "recommendation_authority": False,
    }
    state_payload = {"contract_version": CONTRACT_VERSION, "files": files, "content_hashes": content_hashes}
    for destination, payload in ((state_path, state_payload), (report_path, report)):
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    return report
