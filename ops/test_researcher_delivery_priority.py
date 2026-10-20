"""The researcher must not starve external delivery work behind internal rework."""
from core.task_roles import Researcher
from ops.test_support import FixtureTaskPool


def _noise(pool, title):
    return pool.create_task(title=title, priority="high", tags=["from_obs", "error_handling"])


def _delivery(pool, title, path="docs/WILL.md", priority="high"):
    return pool.create_task(
        title=title,
        priority=priority,
        tags=["external_target", "delivery:physical"],
        outputs={
            "delivery": {
                "required_path": path,
                "success_metric": "file_exists_nonempty",
                "domain": "document",
            }
        },
    )


def test_delivery_task_is_picked_before_older_internal_rework(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    old_noise = _noise(pool, "internal rework A")
    old_noise.audit_log.append({"event": "transition", "to": "review"})
    delivery = _delivery(pool, "external will")

    researcher = Researcher(pool)
    picked = researcher.pick_up_task(priority="any")

    assert picked.task_id == delivery.task_id


def test_priority_ordering_is_not_weakened(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    _delivery(pool, "high priority delivery", path="docs/HIGH.md")
    _delivery(pool, "critical priority delivery", path="docs/CRITICAL.md", priority="critical")

    researcher = Researcher(pool)
    assert researcher.pick_up_task(priority="any").title == "critical priority delivery"


def test_internal_work_still_gets_picked_when_it_is_the_only_work(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    _noise(pool, "internal rework A")
    researcher = Researcher(pool)
    assert researcher.pick_up_task(priority="any") is not None


def test_delivery_ordering_is_stable_within_a_group(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    first = _delivery(pool, "delivery one", path="docs/ONE.md")
    second = _delivery(pool, "delivery two", path="docs/TWO.md")

    ordered = Researcher._delivery_first([first, second])
    assert [task.task_id for task in ordered] == [first.task_id, second.task_id]