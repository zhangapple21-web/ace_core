import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.web_scout import WebScout


def test_video_mine_sources_are_registered_and_prioritized():
    with tempfile.TemporaryDirectory() as temp_dir:
        scout = WebScout(Path(temp_dir), lexicon=None, memory_index=None, task_pool=None)
        assert scout._sources["github_video_short_drama"]["priority"] > scout._sources["github_ai_agents"]["priority"]
        assert scout._sources["github_video_consistency"]["domain"] == "video_kingdom"
        assert scout._sources["github_video_audio"]["domain"] == "video_kingdom"
        assert "video" in scout._interest_keywords
        assert "storyboard" in scout._interest_keywords


def test_video_mine_source_is_selected_before_generic_sources():
    with tempfile.TemporaryDirectory() as temp_dir:
        scout = WebScout(Path(temp_dir), lexicon=None, memory_index=None, task_pool=None)
        assert scout._decide_source() == "github_video_short_drama"


def test_video_repo_description_is_relevant():
    with tempfile.TemporaryDirectory() as temp_dir:
        scout = WebScout(Path(temp_dir), lexicon=None, memory_index=None, task_pool=None)
        assert scout._is_relevant({
            "name": "story-claw",
            "description": "AI short-drama storyboard and video pipeline with character consistency",
        })


if __name__ == "__main__":
    test_video_mine_sources_are_registered_and_prioritized()
    test_video_mine_source_is_selected_before_generic_sources()
    test_video_repo_description_is_relevant()
    print("video web scout checks passed")
