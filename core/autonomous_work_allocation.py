"""Thin read-only allocation view over the existing ACE work producers."""

from typing import Any, Dict, Iterable


WORK_CATEGORIES = (
    "LOCAL",
    "LEARNING",
    "REASONING",
    "STRATEGIC",
    "EXECUTION",
    "EXPLORATION",
    "FINANCIAL_RESEARCH",
)


class AutonomousWorkAllocation:
    """Classify existing lawful work without creating or dispatching tasks."""

    def __init__(self, task_pool):
        self.task_pool = task_pool

    @staticmethod
    def _category(task) -> str:
        outputs = task.outputs if isinstance(task.outputs, dict) else {}
        admission = outputs.get("admission", {})
        discovery = outputs.get("discovery", {})
        source_type = str(admission.get("source_type", "")).lower() if isinstance(admission, dict) else ""
        task_type = str(discovery.get("task_type", "")).lower() if isinstance(discovery, dict) else ""
        tags = {str(tag).lower() for tag in task.tags or []}
        if not task_type:
            task_type = next(
                (tag.split(":", 1)[1] for tag in tags if tag.startswith("task_type:")),
                "",
            )
        joined = " ".join({source_type, task_type, *tags, str(task.creator).lower()})

        financial_tags = {"financial", "financial_research", "stock", "a_share", "a股"}
        if "non_stock" not in tags and (
            bool(tags & financial_tags)
            or source_type in financial_tags
            or task_type == "financial_research"
        ):
            return "FINANCIAL_RESEARCH"
        if source_type == "learning" or "learning" in outputs or "daily_learning" in outputs:
            return "LEARNING"
        if task_type == "strategic":
            return "STRATEGIC"
        if task_type == "execution":
            return "EXECUTION"
        if task_type == "reasoning":
            return "REASONING"
        if any(token in joined for token in ("exploration", "discovery", "observer")):
            return "EXPLORATION"
        return "LOCAL"

    def report(self, lifecycle_result: Dict[str, Any]) -> Dict[str, Any]:
        categories = {
            name: {"count": 0, "representative_task_ids": []}
            for name in WORK_CATEGORIES
        }
        seen = set()
        for status in ("pending", "active", "review", "approved"):
            for task in self.task_pool.list_tasks(status=status, limit=10000):
                if task.task_id in seen or task.outputs.get("terminal_non_convergent"):
                    continue
                seen.add(task.task_id)
                category = self._category(task)
                bucket = categories[category]
                bucket["count"] += 1
                if len(bucket["representative_task_ids"]) < 5:
                    bucket["representative_task_ids"].append(task.task_id)

        total = sum(bucket["count"] for bucket in categories.values())
        daily_learning = lifecycle_result.get("daily_learning")
        discovery = lifecycle_result.get("discovery")
        return {
            "outcome": "WORK_AVAILABLE" if total else "NO_VALID_AUTONOMOUS_WORK",
            "total_existing_work": total,
            "categories": categories,
            "daily_learning": daily_learning,
            "discovery": discovery,
            "tasks_created_by_existing_producers": {
                "observer": lifecycle_result.get("new_tasks", 0),
                "discovery": lifecycle_result.get("discovery_tasks", 0),
                "file_scanner": lifecycle_result.get("fragment_tasks", 0),
                "mine_seed": lifecycle_result.get("mine_seed_tasks", 0),
            },
            # This coordinator only classifies persisted work.  Keep the
            # assertion scoped to this allocator instead of presenting an
            # unverified global claim about every upstream producer.
            "allocation_mode": "read_only_existing_work",
            "allocator_created_task_count": 0,
            "no_synthetic_work_by_allocator": True,
        }
