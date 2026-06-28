#!/usr/bin/env python3
"""
归档 approved 队列中的所有任务

职责：Archivist 的自动执行器
- 检查 approved 目录
- 对每个任务执行归档
- 记录经验沉积
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool_dir = base_dir / "task_pool"
    task_pool = TaskPool(str(task_pool_dir))
    
    approved_dir = task_pool_dir / "approved"
    if not approved_dir.exists():
        print("approved 目录不存在")
        return
    
    approved_tasks = list(approved_dir.glob("*.json"))
    print(f"approved 队列任务数: {len(approved_tasks)}")
    
    archived = 0
    skipped = 0
    
    for task_file in approved_tasks:
        task_id = task_file.stem
        task = task_pool.load_task(task_id)
        if not task:
            print(f"  [WARN] 无法加载任务: {task_id}")
            skipped += 1
            continue
        
        # 检查是否是 approved 状态
        if task.status != "approved":
            print(f"  [SKIP] {task_id} 状态为 {task.status}，非 approved")
            skipped += 1
            continue
        
        # 归档
        try:
            # 格式化归档内容
            archive_note = f"## 任务归档: {task.task_id}\n"
            archive_note += f"**标题**: {task.title}\n"
            archive_note += f"**假设**: {task.hypothesis or '无'}\n"
            archive_note += f"**证据数**: {len(task.evidence)}\n"
            archive_note += f"**重审次数**: {task.review_count}\n"
            
            # 移动到 archived
            task_pool.move_task(task_id, "archived", actor="auto_archivist",
                              reason=f"自动归档: approved 队列积压清理")
            
            archived += 1
            print(f"  [ARCHIVED] {task_id}")
            
        except Exception as e:
            print(f"  [ERROR] {task_id}: {e}")
            skipped += 1
    
    print()
    print("=" * 50)
    print("归档完成")
    print(f"  已归档: {archived} 个")
    print(f"  跳过: {skipped} 个")


if __name__ == "__main__":
    main()
