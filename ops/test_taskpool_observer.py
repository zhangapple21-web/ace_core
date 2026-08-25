import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.taskpool_observer import replay_window


POOL_DIR = Path(__file__).resolve().parent.parent / "task_pool"
WINDOW_START = "2026-08-24T18:00:45.1601767+08:00"
WINDOW_END = "2026-08-24T18:26:37.8244696+08:00"


def test_historical_window_replays_claims_and_following_transitions():
    report = replay_window(POOL_DIR, WINDOW_START, WINDOW_END)

    assert report["counts"] == {
        "claims": 6,
        "research": 6,
        "validation": 6,
    }
    assert [record["task_id"] for record in report["claims"]] == [
        "RQ-20260823-060",
        "RQ-20260823-061",
        "RQ-20260823-062",
        "RQ-20260823-009",
        "RQ-20260823-063",
        "RQ-20260823-070",
    ]
    medium_claim = next(record for record in report["claims"] if record["task_id"] == "RQ-20260823-009")
    assert medium_claim["priority"] == "medium"
    assert medium_claim["research"] is not None
    assert medium_claim["validation"] is not None
    assert medium_claim["fencing_token"] >= medium_claim["claim_count"] >= 1
    assert medium_claim["last_claimed_at"] <= medium_claim["latest_claim_at"]
    assert medium_claim["last_claimed_at"] >= medium_claim["at"]
    assert report["inconsistencies"] == []


if __name__ == "__main__":
    test_historical_window_replays_claims_and_following_transitions()
    print("TaskPool historical observer tests passed")
