#!/usr/bin/env python3
"""Back up ACE runtime data needed to restore the task lifecycle."""

import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

EXCLUDED_PARTS = (".env", "secret", "token", "credential", "customer")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ignore_sensitive(directory: str, names: list[str]) -> set[str]:
    ignored = {".task_pool.lock"}
    if Path(directory).name == "memory":
        ignored.add("daily_learning")
    for name in names:
        lowered = name.lower()
        if lowered.endswith(".tmp") or any(part in lowered for part in EXCLUDED_PARTS):
            ignored.add(name)
    return ignored


def _asset_manifest(name: str, destination: Path, relative_path: Path) -> dict:
    files = []
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            files.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
            )
    return {"name": name, "path": relative_path.as_posix(), "files": files}


def _runtime_assets(base_dir: Path) -> list[tuple[str, Path, Path]]:
    return [
        ("task_pool", base_dir / "task_pool", Path("task_pool")),
        (
            "memory",
            base_dir / "06_RUNTIME" / "ace" / "data" / "memory",
            Path("06_RUNTIME/ace/data/memory"),
        ),
        (
            "daily_learning",
            base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "daily_learning",
            Path("06_RUNTIME/ace/data/memory/daily_learning"),
        ),
        (
            "observations",
            base_dir / "06_RUNTIME" / "ace" / "data" / "observations",
            Path("06_RUNTIME/ace/data/observations"),
        ),
        ("knowledge", base_dir / "09_KNOWLEDGE", Path("09_KNOWLEDGE")),
        (
            "fragment_index",
            base_dir / "02_FRAGMENT_INDEX",
            Path("02_FRAGMENT_INDEX"),
        ),
    ]


def cleanup_old_backups(backup_root: Path, keep_count: int = 10) -> int:
    backups = sorted(
        [item for item in backup_root.iterdir() if item.is_dir() and item.name.startswith("backup_")],
        key=lambda item: item.name,
        reverse=True,
    )
    removed = 0
    for old_backup in backups[keep_count:]:
        shutil.rmtree(old_backup)
        removed += 1
    return removed


def backup_runtime(base_dir: Path, keep_count: int = 10) -> tuple[Path, dict]:
    base_dir = Path(base_dir).resolve()
    backup_root = base_dir / "06_RUNTIME" / "ace" / "data" / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = backup_root / f"backup_{timestamp}"
    backup_dir.mkdir()
    assets = []
    for name, source, relative_path in _runtime_assets(base_dir):
        if not source.exists():
            assets.append(
                {"name": name, "path": relative_path.as_posix(), "status": "missing", "files": []}
            )
            continue
        destination = backup_dir / relative_path
        shutil.copytree(source, destination, ignore=_ignore_sensitive)
        asset = _asset_manifest(name, destination, relative_path)
        asset["status"] = "backed_up"
        assets.append(asset)
    manifest = {
        "version": 2,
        "timestamp": datetime.now().isoformat(),
        "assets": assets,
        "old_backups_removed": cleanup_old_backups(backup_root, keep_count),
    }
    (backup_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return backup_dir, manifest


def restore_backup(backup_dir: Path, target_dir: Path) -> dict:
    backup_dir = Path(backup_dir).resolve()
    target_dir = Path(target_dir).resolve()
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    if target_dir.exists() and any(target_dir.iterdir()):
        raise ValueError("restore target must be empty")
    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    valid = manifest.get("version") == 2
    restored_files = 0
    for asset in manifest.get("assets", []):
        if asset.get("status") == "missing":
            continue
        source = backup_dir / asset["path"]
        destination = target_dir / asset["path"]
        shutil.copytree(source, destination, dirs_exist_ok=True)
        for item in asset["files"]:
            path = destination / item["path"]
            valid = valid and path.exists() and _sha256(path) == item["sha256"]
            restored_files += 1
    return {"valid": valid, "restored_files": restored_files}


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    backup_dir, manifest = backup_runtime(base_dir)
    total_size = sum(item.stat().st_size for item in backup_dir.rglob("*") if item.is_file())
    print(f"Backup directory: {backup_dir}")
    print(f"Backup complete: {len(manifest['assets'])} assets")
    print(f"Backup size: {total_size / (1024 * 1024):.2f} MB")


if __name__ == "__main__":
    main()
