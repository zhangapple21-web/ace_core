#!/usr/bin/env python3
"""
清理 review 队列中的死循环任务

规则：
- review_count >= 3 → 强制 approval（终审保护）
- review_count >= 2 且证据不足 → 降级为 archive（放弃继续考古）
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool_dir = base_dir / "task_pool"
    task_pool = TaskPool(str(task_pool_dir))
    
    review_dir = task_pool_dir / "review"
    if not review_dir.exists():
        print("review 目录不存在")
        return
    
    review_tasks = list(review_dir.glob("*.json"))
    print(f"review 队列任务数: {len(review_tasks)}")
    
    results = {
        "forced_approval": [],
        "archived": [],
        "skipped": [],
    }
    
    for task_file in review_tasks:
        task_id = task_file.stem
        task = task_pool.load_task(task_id)
        if not task:
            print(f"  [WARN] 无法加载任务: {task_id}")
            continue
        
        # 读取 review_count
        review_count = task.review_count
        
        if review_count >= 3:
            # 终审保护：强制 approval
            task_pool.move_task(task_id, "approved", actor="auto_curator", 
                              reason=f"终审保护：review_count={review_count} >= 3，强制批准")
            results["forced_approval"].append(task_id)
            print(f"  [APPROVED] {task_id} (review_count={review_count})")
            
        elif review_count >= 2:
            # 降级为 archive（证据不足，放弃继续考古）
            # 先检查是否有足够的证据
            evidence_count = len(task.evidence) if task.evidence else 0
            if evidence_count < 3:
                task_pool.move_task(task_id, "archived", actor="auto_curator",
                                  reason=f"考古证据不足：review_count={review_count}, evidence={evidence_count}")
                results["archived"].append(task_id)
                print(f"  [ARCHIVED] {task_id} (review_count={review_count}, evidence={evidence_count})")
            else:
                # 有足够证据，强制 approval
                task_pool.move_task(task_id, "approved", actor="auto_curator",
                                  reason=f"有足够证据：review_count={review_count}, evidence={evidence_count}，强制批准")
                results["forced_approval"].append(task_id)
                print(f"  [APPROVED] {task_id} (review_count={review_count}, evidence={evidence_count})")
        else:
            results["skipped"].append(task_id)
            print(f"  [SKIP] {task_id} (review_count={review_count})")
    
    print()
    print("=" * 50)
    print("清理完成")
    print(f"  强制批准: {len(results['forced_approval'])} 个")
    print(f"  归档: {len(results['archived'])} 个")
    print(f"  跳过: {len(results['skipped'])} 个")


if __name__ == "__main__":
    main()
