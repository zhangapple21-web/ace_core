from core.task import TaskPool as ProductionTaskPool


class FixtureTaskPool(ProductionTaskPool):
    def create_task(self, *args, **kwargs):
        if kwargs.get("admission") is None:
            title = kwargs.get("title") or (args[0] if args else "task")
            kwargs["admission"] = {
                "source_type": "system_observation",
                "source_ref": f"test-fixture:{title}",
                "why_now": "exercise runtime behavior",
                "evidence": ["test-fixture"],
                "expected_result": "test result",
                "verification_method": "pytest assertion",
                "risk": "test-only",
                "estimated_scope": "test",
            }
        return super().create_task(*args, **kwargs)

