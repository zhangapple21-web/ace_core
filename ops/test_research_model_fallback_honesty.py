"""Research must not be reported as done when no model took part in it.

The failure this pins, measured on 2026-10-18:

    228 archived `tension_question` tasks, 3 distinct questions
    (thinking_drought / fa_duty_gap / learn_without_use),
    0 with a `model_execution` trace,
    0 with a `model_research_result`,
    228 with byte-identical result payloads whose single candidate was
    "核心假设：验证系统 / 来源 / obs", confidence 0.8, reasoning
    "基于任务标题的核心概念提取".

The cause was correct behaviour in a different component: those tasks carry
`data_class=PRIVATE`, so the data boundary refused egress with
`DATA_BOUNDARY_BLOCKED:sensitive_data_cannot_egress`. Refusing to send private
data to a model was right. Consuming that refusal silently and then filing an
outcome receipt was not - it made TaskPool's completion counts report research
that never happened.

The contract pinned here: a candidate set built from title tokens is recorded as
such, and the reason the model contributed nothing is carried on the task.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.task import TaskPool


class _BlockedRouter:
    """A router that refuses egress exactly the way the data boundary does."""

    def chat(self, *args, **kwargs):
        return {
            "success": False,
            "content": "",
            "model": "",
            "provider": "",
            "error": "DATA_BOUNDARY_BLOCKED:sensitive_data_cannot_egress",
            "routing": {"selected_route_state": "DATA_BOUNDARY_BLOCKED"},
            "tried_models": [],
            "attempts": [],
        }


class _WorkingRouter:
    def chat(self, *args, **kwargs):
        return {
            "success": True,
            "content": '{"facts": ["the question was read"]}',
            "model": "stub",
            "provider": "stub",
        }


def _researcher(tmp_path, router):
    from core.task_roles import Researcher

    pool = TaskPool(str(tmp_path / "pool"))
    return pool, Researcher(task_pool=pool, llm_router=router)


def _task(pool, task_id="RQ-TEST-001", title="验证系统自问 来源 OBS-1：thinking_drought"):
    return pool.create_task(
        title=title,
        hypothesis="系统在无人点名下提出了一个带 verification_plan 的问题。",
        creator="observation_to_task",
        priority="medium",
        tags=["question_forge", "tension"],
        admission={
            "source_type": "system_observation",
            "source_ref": "OBS-1",
            "why_now": "Observation OBS-1 matched rule tension_question",
            "evidence": [{
                "observation_id": "OBS-1",
                "source_ref": "runtime_observation:OBS-1",
                "category": "anomaly",
                "severity": "medium",
                "description": "thinking_drought",
                "system_state": {"tension_key": "thinking_drought"},
                "rule": "tension_question",
            }],
            "expected_result": "verify the question",
            "verification_method": "re-observe",
            "risk": "internal",
            "estimated_scope": "one observation",
        },
        outputs={"conversion_rule": "tension_question", "data_class": "PRIVATE"},
    )


def _task_with_task_type(pool, task_type, **kw):
    return pool.create_task(
        title="验证系统自问 来源 OBS-1：thinking_drought",
        hypothesis="系统在无人点名下提出了一个带 verification_plan 的问题。",
        creator="observation_to_task",
        priority="medium",
        tags=["question_forge", "tension", f"task_type:{task_type}"],
        admission={
            "source_type": "system_observation",
            "source_ref": "OBS-1",
            "why_now": "Observation OBS-1 matched rule tension_question",
            "evidence": [{
                "observation_id": "OBS-1",
                "source_ref": "runtime_observation:OBS-1",
                "category": "anomaly",
                "severity": "medium",
                "description": "thinking_drought",
                "system_state": {"tension_key": "thinking_drought"},
                "rule": "tension_question",
            }],
            "expected_result": "verify the question",
            "verification_method": "re-observe",
            "risk": "internal",
            "estimated_scope": "one observation",
        },
        outputs=kw.pop("outputs", {}),
    )


class BlockedModelIsNotResearched(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_blocked_model_is_recorded_and_candidates_marked_keyword_only(self):
        pool, researcher = _researcher(self.tmp_path, _BlockedRouter())
        task = _task_with_task_type(pool, "reasoning")

        researcher.research_task(task)

        result = task.result or {}
        self.assertFalse(
            result.get("model_engaged"),
            "a blocked egress must never be reported as model engagement",
        )
        self.assertTrue(result.get("model_attempted"))
        self.assertIn(
            "DATA_BOUNDARY_BLOCKED", str(result.get("model_block_reason", "")),
            "the real reason the model contributed nothing must survive on the task",
        )
        self.assertEqual(
            result.get("candidate_basis"), "title_keywords_only",
            "a title-token candidate set must be labelled as exactly that",
        )

    def test_engaged_model_is_not_labelled_keyword_only(self):
        pool, researcher = _researcher(self.tmp_path, _WorkingRouter())
        task = _task_with_task_type(pool, "reasoning")

        researcher.research_task(task)

        result = task.result or {}
        self.assertTrue(result.get("model_engaged"))
        self.assertEqual(result.get("model_block_reason"), "")
        self.assertEqual(result.get("candidate_basis"), "evidence_or_model")
        self.assertTrue((task.outputs or {}).get("model_research_result"))

    def test_production_default_task_type_never_reaches_a_model(self):
        """The measured production shape: no task_type tag, so no model.

        This is the actual 2026-10-18 condition behind 228 keyword-only results.
        `tension_question` writes no `task_type:` tag, `_model_task_type` returns
        the empty string, and only the `reasoning` profile has model_enabled set.
        The research then completed anyway.  What is pinned here is that this is
        now *visible* on the task instead of silently indistinguishable from
        research.
        """
        pool, researcher = _researcher(self.tmp_path, _BlockedRouter())
        task = _task(pool)  # no task_type tag, exactly as production files it

        researcher.research_task(task)

        result = task.result or {}
        self.assertFalse(result.get("model_engaged"))
        self.assertEqual(
            result.get("candidate_basis"), "title_keywords_only",
            "an untagged task researches by keywords only, and must say so",
        )
        self.assertEqual(result.get("model_block_reason"), "", "no attempt was made")

    def test_the_failure_is_visible_without_reading_the_source(self):
        """A reader of task.result alone must be able to see what happened."""
        pool, researcher = _researcher(self.tmp_path, _BlockedRouter())
        task = _task_with_task_type(pool, "reasoning")

        researcher.research_task(task)

        result = task.result
        self.assertIsNotNone(result)
        for key in ("model_engaged", "model_attempted", "model_block_reason", "candidate_basis"):
            self.assertIn(key, result, f"{key} missing from the research result")


if __name__ == "__main__":
    unittest.main()