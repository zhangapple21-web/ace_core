import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.task import TaskPool
from core.task_roles import Observer


def _admission(ref):
    return {
        "source_type": "maintenance",
        "source_ref": ref,
        "why_now": "test gap discovery",
        "evidence": [{"source": ref, "detail": "test"}],
        "expected_result": "gap found",
        "verification_method": "recheck",
        "risk": "test only",
        "estimated_scope": "test",
    }


def _observer(pool, daemon_state=None):
    return Observer(task_pool=pool, lexicon=None, memory_index=None,
                    daemon_state=daemon_state or {}, experience_deposition=None)


def test_discovers_missing_fuse_backlog():
    with tempfile.TemporaryDirectory() as td:
        pool = TaskPool(td)
        for i in range(3):
            t = pool.create_task(f"gap-t-{i}", creator="observer", admission=_admission(f"gap-{i}"))
            pool.block_task(t.task_id, reason="wait", actor="test", block_type="manual_gate_blocked")
        titles = [c["title"] for c in _observer(pool)._generate_candidates()]
        assert "存量非收敛任务缺熔断方向待补" in titles


def test_no_fuse_gap_when_clean():
    with tempfile.TemporaryDirectory() as td:
        pool = TaskPool(td)
        titles = [c["title"] for c in _observer(pool)._generate_candidates()]
        assert "存量非收敛任务缺熔断方向待补" not in titles
        assert "低优先级碎沫堆积需批量分诊" not in titles


def test_discovers_low_flood():
    with tempfile.TemporaryDirectory() as td:
        pool = TaskPool(td)
        for i in range(16):
            pool.create_task(f"flood-{i}", creator="observer", priority="low",
                             admission=_admission(f"flood-{i}"))
        titles = [c["title"] for c in _observer(pool)._generate_candidates()]
        assert "低优先级碎沫堆积需批量分诊" in titles


def test_discovers_daemon_deaths():
    with tempfile.TemporaryDirectory() as td:
        pool = TaskPool(td)
        obs = _observer(pool, daemon_state={"death_count": 102, "consecutive_misses": 0})
        titles = [c["title"] for c in obs._generate_candidates()]
        assert "daemon死亡计数过百需根因复盘" in titles


def test_titles_stable_for_dedup():
    with tempfile.TemporaryDirectory() as td:
        pool = TaskPool(td)
        t = pool.create_task("gap-t-0", creator="observer", admission=_admission("gap-0"))
        pool.block_task(t.task_id, reason="wait", actor="test", block_type="manual_gate_blocked")
        first = [c["title"] for c in _observer(pool)._generate_candidates()]
        second = [c["title"] for c in _observer(pool)._generate_candidates()]
        assert first == second


if __name__ == "__main__":
    test_discovers_missing_fuse_backlog()
    test_no_fuse_gap_when_clean()
    test_discovers_low_flood()
    test_discovers_daemon_deaths()
    test_titles_stable_for_dedup()
    print("gap self-discovery checks passed")
