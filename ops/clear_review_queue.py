#!/usr/bin/env python3
"""
Report review tasks that require additional evidence.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool = TaskPool(base_dir / "task_pool")
    review_tasks = task_pool.list_tasks(status="review", limit=10000)

    print(f"review queue tasks: {len(review_tasks)}")
    needs_research = 0
    stable = 0

    for task in review_tasks:
        evidence_count = len(task.evidence)
        if task.review_count >= 2:
            needs_research += 1
            print(
                f"  [RESEARCH] {task.task_id}: "
                f"review_count={task.review_count}, evidence={evidence_count}"
            )
        else:
            stable += 1
            print(f"  [REVIEW] {task.task_id}: evidence={evidence_count}")

    print()
    print("=" * 50)
    print("Review queue report")
    print(f"  Needs research: {needs_research}")
    print(f"  Awaiting review: {stable}")


if __name__ == "__main__":
    main()
