#!/usr/bin/env python3
"""
清理过期任务 — 维护系统健康

规则：
- rejected 目录：保留最近 30 天的任务
- graveyard 目录：保留最近 14 天的任务
- archived 目录：只保留最近 100 个任务（按更新时间）
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool_dir = base_dir / "task_pool"
    task_pool = TaskPool(str(task_pool_dir))
    
    today = datetime.now()
    cutoff_rejected = today - timedelta(days=30)
    cutoff_graveyard = today - timedelta(days=14)
    max_archived = 100
    
    results = {
        "rejected": {"cleaned": 0, "kept": 0},
        "graveyard": {"cleaned": 0, "kept": 0},
        "archived": {"cleaned": 0, "kept": 0},
    }
    
    # === 清理 rejected ===
    rejected_dir = task_pool_dir / "rejected"
    if rejected_dir.exists():
        for task_file in list(rejected_dir.glob("*.json")):
            task = task_pool.load_task(task_file.stem)
            if task:
                created = datetime.fromisoformat(task.created_at)
                if created < cutoff_rejected:
                    task_file.unlink()
                    results["rejected"]["cleaned"] += 1
                else:
                    results["rejected"]["kept"] += 1
    print(f"[rejected] 清理: {results['rejected']['cleaned']}, 保留: {results['rejected']['kept']}")
    
    # === 清理 graveyard ===
    graveyard_dir = task_pool_dir / "graveyard"
    if graveyard_dir.exists():
        for task_file in list(graveyard_dir.glob("*.json")):
            task = task_pool.load_task(task_file.stem)
            if task:
                created = datetime.fromisoformat(task.created_at)
                if created < cutoff_graveyard:
                    task_file.unlink()
                    results["graveyard"]["cleaned"] += 1
                else:
                    results["graveyard"]["kept"] += 1
    print(f"[graveyard] 清理: {results['graveyard']['cleaned']}, 保留: {results['graveyard']['kept']}")
    
    # === 限制 archived 数量 ===
    archived_dir = task_pool_dir / "archived"
    if archived_dir.exists():
        archived_tasks = []
        for task_file in archived_dir.glob("*.json"):
            task = task_pool.load_task(task_file.stem)
            if task:
                updated = datetime.fromisoformat(task.updated_at)
                archived_tasks.append((updated, task_file))
        
        archived_tasks.sort(reverse=True)  # 按更新时间倒序
        
        if len(archived_tasks) > max_archived:
            # 删除超过上限的旧任务
            for _, task_file in archived_tasks[max_archived:]:
                task_file.unlink()
                results["archived"]["cleaned"] += 1
            results["archived"]["kept"] = max_archived
        else:
            results["archived"]["kept"] = len(archived_tasks)
    print(f"[archived] 清理: {results['archived']['cleaned']}, 保留: {results['archived']['kept']}")
    
    total_cleaned = sum(v["cleaned"] for v in results.values())
    print()
    print("=" * 50)
    print(f"清理完成，共清理 {total_cleaned} 个过期任务")


if __name__ == "__main__":
    main()
