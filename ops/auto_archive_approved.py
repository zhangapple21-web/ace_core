#!/usr/bin/env python3
"""
Archive Guardian-approved tasks through the canonical Archivist path.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool
from core.task_roles import Archivist


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool = TaskPool(base_dir / "task_pool")
    archivist = Archivist(task_pool)
    approved_tasks = task_pool.list_tasks(status="approved", limit=10000)

    print(f"approved queue tasks: {len(approved_tasks)}")
    archived = 0
    skipped = 0

    for task in approved_tasks:
        if archivist.archive_task(task):
            archived += 1
            print(f"  [ARCHIVED] {task.task_id}")
        else:
            skipped += 1
            print(f"  [SKIP] {task.task_id}: guardian decision required")

    print()
    print("=" * 50)
    print("Archive complete")
    print(f"  Archived: {archived}")
    print(f"  Skipped: {skipped}")


if __name__ == "__main__":
    main()
