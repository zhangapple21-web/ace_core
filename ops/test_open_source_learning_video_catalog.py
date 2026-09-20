import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.open_source_learning import OpenSourceLearningBacklog
from core.task import TaskPool


def test_video_mining_has_governed_backlog_candidates():
    with tempfile.TemporaryDirectory() as temp_dir:
        backlog = OpenSourceLearningBacklog(TaskPool(str(Path(temp_dir) / "pool")))
        candidates = backlog.candidates()
        assert candidates
        candidate, evidence = candidates[0]
        assert candidate.title == "考古 Story Claw 短剧资产与 VLM 复核"
        assert candidate.metadata["learning"]["requires_miner"] is True
        assert len(evidence) == 2
        assert candidate.metadata["open_source_catalog"]["disposition"] == "ADAPT"


if __name__ == "__main__":
    test_video_mining_has_governed_backlog_candidates()
    print("video open-source mining backlog checks passed")
