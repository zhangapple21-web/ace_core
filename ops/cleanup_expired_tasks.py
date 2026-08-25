#!/usr/bin/env python3
"""
Report task retention candidates without deleting lifecycle records.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.task import TaskPool


def count_candidates(tasks, cutoff):
    return sum(
        datetime.fromisoformat(task.created_at) < cutoff
        for task in tasks
    )


def main():
    base_dir = Path(__file__).parent.parent.resolve()
    task_pool = TaskPool(base_dir / "task_pool")
    today = datetime.now()

    rejected_candidates = count_candidates(
        task_pool.list_tasks(status="rejected", limit=10000),
        today - timedelta(days=30),
    )
    graveyard_candidates = count_candidates(
        task_pool.list_tasks(status="graveyard", limit=10000),
        today - timedelta(days=14),
    )
    archived_count = len(task_pool.list_tasks(status="archived", limit=10000))

    print("Retention report")
    print(f"  Rejected older than 30 days: {rejected_candidates}")
    print(f"  Graveyard older than 14 days: {graveyard_candidates}")
    print(f"  Archived records retained: {archived_count}")
    print("  No task records were deleted.")


if __name__ == "__main__":
    main()
