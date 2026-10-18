"""A ring of tasks quoting each other is not evidence.

Measured on 2026-10-18: 59 tasks in `task_pool/blocked`, all created by
`free_zone_reflection_relay`, all blocked with the same reason
"相同证据集重复验证达到上限，等待人工或外部新证据", all holding exactly two
evidence records, and those two records identical across all 59 tasks:

    archivist:4749f239  ## 任务ID: RQ-20261013-016  回看自由区结果 EXP-...
    archivist:d24fee2c  ## 任务ID: RQ-20261013-015  回看自由区结果 EXP-...

Each task's evidence was two other task cards of the same kind. Validator scored
the pair as corroboration, could not converge against a closed ring, and the ring
parked. The verdict was right; the reason was wrong - the pair was never
independent - and it was unreachable, because re-validating a ring cannot break it.

`_is_reuse_pointer` already excluded `knowledge_join:` pointers from
corroboration. The task-card shape escaped it by arriving under `archivist:`.
This pins both halves: the ring is excluded, and real observations are not.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.task_roles import _is_reuse_pointer


def _card(task_id: str, title: str) -> dict:
    return {
        "source": f"archivist:{task_id.split('-')[-1]}",
        "content": f"## 任务ID: {task_id}\n**标题**: {title}\n**创建者**: free_zone_reflection_relay",
        "type": "task_card",
    }


class TaskCardEvidenceIsNotCorroboration(unittest.TestCase):
    def test_task_card_evidence_is_a_pointer_not_an_observation(self):
        card = _card("RQ-20261013-016", "回看自由区结果 EXP-20261005103527186895-FREEZONE-628C943389FE")
        self.assertTrue(
            _is_reuse_pointer(card),
            "an archived task card is the system quoting itself, never corroboration",
        )

    def test_the_two_evidence_of_the_measured_ring_are_both_pointers(self):
        """Both halves of the 2026-10-13 ring, exactly as stored."""
        ring = [
            _card("RQ-20261013-016", "回看自由区结果 EXP-20261005103527186895-FREEZONE-628C943389FE"),
            _card("RQ-20261013-015", "回看自由区结果 EXP-20261004103435888673-FREEZONE-AA5536C931BE"),
        ]
        self.assertEqual(len(ring), 2)
        self.assertTrue(all(_is_reuse_pointer(item) for item in ring))

    def test_declared_reuse_pointer_still_excluded(self):
        self.assertTrue(_is_reuse_pointer({"source": "knowledge_join:abc", "content": "x"}))

    def test_real_observations_are_not_excluded(self):
        """The guard must not become a way to discard genuine evidence."""
        for item in (
            {"source": "memory:abc", "content": "an observed condition"},
            {"source": "external:https://example/doc", "content": "upstream text"},
            {"source": "lexicon:某概念", "content": "词库概念定义"},
            {"source": "archivist:aa", "content": "## 自由区实验摘要\nINCONCLUSIVE"},
        ):
            self.assertFalse(
                _is_reuse_pointer(item),
                f"real evidence must remain countable: {item}",
            )

    def test_malformed_records_do_not_raise(self):
        for item in (None, {}, {"source": None}, {"content": None}, "not a dict", 7):
            self.assertFalse(_is_reuse_pointer(item))


if __name__ == "__main__":
    unittest.main()