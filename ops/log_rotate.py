#!/usr/bin/env python3
"""
ACE 日志轮转脚本 (ID-07)

按大小/天数切割日志，自动压缩，保留周期。

配置（通过 ace_config.json 或默认值）：
  log_rotate:
    max_size_mb: 50       # 单文件最大大小
    max_days: 30          # 保留天数
    max_files: 10         # 最多保留文件数
    compress: true        # 是否压缩旧日志

支持的日志类型：
  - daemon_state.json 错误记录（轮转错误历史）
  - archive 归档文件（按月份归档）
  - 每日摘要（按周归档）

用法：
  python ops/log_rotate.py
  python ops/log_rotate.py --dry-run   # 预览不执行
  python ops/log_rotate.py --verbose   # 详细输出
"""

import json
import sys
import os
import gzip
import shutil
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

DEFAULT_CONFIG = {
    "max_size_mb": 50,
    "max_days": 30,
    "max_files": 20,
    "compress": True,
}


def get_config() -> dict:
    cfg_path = BASE_DIR / "ace_config.json"
    if cfg_path.is_file():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg.get("log_rotate", {})}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def rotate_file(file_path: Path, config: dict, dry_run: bool, verbose: bool) -> list:
    """轮转单个文件，返回操作列表"""
    actions = []
    if not file_path.is_file():
        return actions

    size_mb = file_path.stat().st_size / (1024 * 1024)
    max_size = config["max_size_mb"]

    if size_mb < max_size:
        if verbose:
            print(f"  [SKIP] {file_path.name} ({size_mb:.1f}MB < {max_size}MB)")
        return actions

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    rotated_name = f"{file_path.stem}.{ts}{file_path.suffix}"
    rotated_path = file_path.parent / rotated_name

    if dry_run:
        actions.append(f"将 {file_path.name} 重命名为 {rotated_name}")
    else:
        shutil.move(str(file_path), str(rotated_path))
        actions.append(f"已轮转: {file_path.name} -> {rotated_name}")

    if config["compress"]:
        gz_path = rotated_path.with_suffix(rotated_path.suffix + ".gz")
        if dry_run:
            actions.append(f"将压缩为 {gz_path.name}")
        else:
            with open(rotated_path, "rb") as f_in:
                with gzip.open(gz_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            rotated_path.unlink()
            actions.append(f"已压缩: {gz_path.name}")

    return actions


def cleanup_old(file_pattern: str, config: dict, dry_run: bool, verbose: bool) -> list:
    """清理过期的轮转文件"""
    actions = []
    base_dir = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory"
    if not base_dir.is_dir():
        base_dir = BASE_DIR / "06_RUNTIME" / "ace" / "data"

    files = sorted(base_dir.glob(file_pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    max_files = config["max_files"]
    if len(files) > max_files:
        to_delete = files[max_files:]
        for f in to_delete:
            if dry_run:
                actions.append(f"将删除: {f.name} (超出保留数量)")
            else:
                f.unlink()
                actions.append(f"已删除: {f.name} (超出保留数量)")

    max_days = config["max_days"]
    cutoff = datetime.now() - timedelta(days=max_days)
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            if dry_run:
                actions.append(f"将删除: {f.name} (超过{max_days}天)")
            else:
                f.unlink()
                actions.append(f"已删除: {f.name} (超过{max_days}天)")

    return actions


def rotate_daemon_state(config: dict, dry_run: bool, verbose: bool) -> list:
    """轮转 daemon_state.json 中的错误记录（保持文件大小可控）"""
    actions = []
    state_path = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
    if not state_path.is_file():
        return actions

    size_mb = state_path.stat().st_size / (1024 * 1024)
    if size_mb < config["max_size_mb"]:
        if verbose:
            print(f"  [OK] daemon_state.json ({size_mb:.1f}MB)")
        return actions

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)

        errors = state.get("errors", [])
        if len(errors) > 100:
            old_errors = errors[:-50]
            state["errors"] = errors[-50:]

            ts = datetime.now().strftime("%Y%m%d")
            archive_name = f"daemon_errors_archive_{ts}.json"
            archive_path = state_path.parent / archive_name

            if dry_run:
                actions.append(f"将归档 {len(old_errors)} 条旧错误到 {archive_name}")
            else:
                with open(archive_path, "w", encoding="utf-8") as f:
                    json.dump({"archived_at": datetime.now().isoformat(), "errors": old_errors}, f, ensure_ascii=False, indent=2)
                with open(state_path, "w", encoding="utf-8") as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                actions.append(f"已归档 {len(old_errors)} 条旧错误到 {archive_name}")
    except Exception as e:
        actions.append(f"错误: daemon_state 轮转失败 - {e}")

    return actions


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 日志轮转")
    parser.add_argument("--dry-run", action="store_true", help="预览不执行")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    args = parser.parse_args()

    config = get_config()

    print("=" * 55)
    print(f"ACE 日志轮转 — {datetime.now().isoformat()}")
    print("=" * 55)
    print(f"配置: 最大{config['max_size_mb']}MB / 保留{config['max_days']}天 / 最多{config['max_files']}个文件 / 压缩={'开' if config['compress'] else '关'}")
    if args.dry_run:
        print("【预览模式，不实际执行】")
    print()

    all_actions = []

    print("1. 轮转 daemon_state 错误记录")
    actions = rotate_daemon_state(config, args.dry_run, args.verbose)
    all_actions.extend(actions)
    for a in actions:
        print(f"  {a}")
    if not actions and not args.verbose:
        print("  无需轮转")
    print()

    print("2. 清理旧的错误归档")
    actions = cleanup_old("daemon_errors_archive_*.json*", config, args.dry_run, args.verbose)
    all_actions.extend(actions)
    for a in actions:
        print(f"  {a}")
    if not actions and not args.verbose:
        print("  无需清理")
    print()

    print(f"完成。共 {len(all_actions)} 项操作。")
    print("=" * 55)


if __name__ == "__main__":
    main()
