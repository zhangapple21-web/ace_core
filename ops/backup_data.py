#!/usr/bin/env python3
"""
关键数据备份脚本

备份核心数据，防止意外丢失。
备份内容：
- 词库 (lexicon.json)
- 记忆索引 (memory_index.json)
- 碎片索引 (fragment_index.json)
- 守护进程状态 (daemon_state.json)
- 任务池归档 (task_pool/archived/)

备份策略：
- 每次运行生成带时间戳的备份
- 保留最近 10 份备份
- 备份到 06_RUNTIME/ace/data/backups/
"""

import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


def backup_file(src: Path, dst_dir: Path) -> bool:
    """备份单个文件"""
    if not src.exists():
        return False
    try:
        dst = dst_dir / src.name
        shutil.copy2(src, dst)
        return True
    except Exception as e:
        print(f"  [WARN] 备份失败 {src.name}: {e}")
        return False


def copy_dir(src: Path, dst_dir: Path) -> bool:
    """备份整个目录"""
    if not src.exists():
        return False
    try:
        dst = dst_dir / src.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        return True
    except Exception as e:
        print(f"  [WARN] 备份失败 {src.name}: {e}")
        return False


def cleanup_old_backups(backup_root: Path, keep_count: int = 10):
    """清理旧备份，只保留最近 N 份"""
    backups = sorted(
        [d for d in backup_root.iterdir() if d.is_dir() and d.name.startswith("backup_")],
        key=lambda d: d.name,
        reverse=True,
    )
    if len(backups) <= keep_count:
        return 0
    
    removed = 0
    for old_backup in backups[keep_count:]:
        try:
            shutil.rmtree(old_backup)
            removed += 1
        except Exception:
            pass
    return removed


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    data_dir = base_dir / "06_RUNTIME" / "ace" / "data"
    
    backup_root = data_dir / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_root / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"备份目录: {backup_dir}")
    print()
    
    # 需要备份的文件
    files_to_backup = [
        data_dir / "memory" / "lexicon.json",
        data_dir / "memory" / "memory_index.json",
        data_dir / "memory" / "daemon_state.json",
        base_dir / "02_FRAGMENT_INDEX" / "fragment_index.json",
    ]
    
    # 需要备份的目录
    dirs_to_backup = [
        base_dir / "task_pool" / "archived",
    ]
    
    # 备份文件
    print("【备份文件】")
    file_count = 0
    for src in files_to_backup:
        success = backup_file(src, backup_dir)
        status = "OK" if success else "SKIP"
        print(f"  [{status}] {src.name}")
        if success:
            file_count += 1
    
    # 备份目录
    print()
    print("【备份目录】")
    dir_count = 0
    for src in dirs_to_backup:
        success = copy_dir(src, backup_dir)
        status = "OK" if success else "SKIP"
        print(f"  [{status}] {src.name}/")
        if success:
            dir_count += 1
    
    # 清理旧备份
    print()
    print("【清理旧备份】")
    removed = cleanup_old_backups(backup_root, keep_count=10)
    print(f"  已清理 {removed} 份旧备份")
    
    # 生成备份清单
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "files_backed_up": file_count,
        "dirs_backed_up": dir_count,
        "old_backups_removed": removed,
    }
    manifest_file = backup_dir / "manifest.json"
    with open(manifest_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    
    # 计算备份大小
    total_size = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)
    
    print()
    print("=" * 50)
    print(f"备份完成: {file_count} 个文件, {dir_count} 个目录")
    print(f"备份大小: {size_mb:.2f} MB")
    print(f"保留份数: 10 份")


if __name__ == "__main__":
    main()
