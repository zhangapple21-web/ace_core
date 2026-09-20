import json
from pathlib import Path

from core.governed_external_miner import GovernedExternalMiner
from core.task import TaskPool


def _fetcher(url):
    if url.endswith("/license"):
        payload = {
            "content": "TUlUIExpY2Vuc2U=",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
        }
    elif "api.github.com/repos" in url:
        payload = {
            "full_name": "example/story-claw",
            "html_url": "https://github.com/example/story-claw",
            "default_branch": "main",
            "description": "stage-aware short drama pipeline",
            "stargazers_count": 10,
            "updated_at": "2026-09-21T00:00:00Z",
            "license": {"spdx_id": "MIT", "name": "MIT License"},
            "archived": False,
        }
    else:
        return (b"# Story Claw\n\nStage-aware assets, first/last-frame review and retry workflow.", "text/markdown", {})
    return (json.dumps(payload).encode("utf-8"), "application/json", {})


class _Miner:
    def chat(self, **kwargs):
        return {
            "success": True,
            "provider": "test",
            "model": "test-model",
            "tried_models": ["test:test-model"],
            "content": json.dumps(
                {
                    "facts": ["README and metadata were fetched"],
                    "compatibility": ["map stage assets to ACE states"],
                    "risks": ["must not execute external code"],
                    "objections": ["one upstream repository is not independent validation"],
                    "unknowns": ["runtime quality on local GPU"],
                    "next_verification": ["compare with local contract tests"],
                    "disposition": "ADAPT",
                }
            ),
        }


def test_governed_external_miner_fetches_calls_miner_and_queues_once(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    miner = GovernedExternalMiner(
        base_dir=tmp_path,
        task_pool=pool,
        miner_pool=_Miner(),
        targets=[
            {
                "id": "story-claw",
                "title": "考古 Story Claw",
                "repository": "https://github.com/example/story-claw",
                "objective": "核验阶段化资产和 QC",
                "disposition": "ADAPT",
            }
        ],
        fetcher=_fetcher,
    )

    first = miner.run_once()
    assert first["status"] == "QUEUED"
    assert first["chain"] == {
        "web_scout": "FETCHED",
        "miner_pool": "COMPLETED",
        "task_pool": "CREATED",
        "researcher": "PENDING",
        "validator": "PENDING",
        "guardian": "PENDING",
    }
    task = pool.load_task(first["task_id"])
    assert task is not None
    assert task.creator == "governed_web_scout"
    assert task.outputs["external_mining"]["fetched"]["fingerprint"]
    assert len(task.outputs["external_mining"]["fetched"]["evidence"]) == 3
    assert task.outputs["admission"]["source_type"] == "learning"

    second = miner.run_once()
    assert second["status"] == "IDEMPOTENT_NO_NEW_TARGET"
    assert len(pool.list_tasks(limit=20)) == 1
    report = json.loads((tmp_path / "07_SANDBOX/free_research/reports/governed_external_mining_latest.json").read_text(encoding="utf-8"))
    assert report["chain"]["web_scout"] == "NO_NEW_TARGET"
