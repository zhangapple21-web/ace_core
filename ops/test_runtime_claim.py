import json
import os
import pytest

from core.runtime_claim import RuntimeClaimStore


@pytest.mark.skipif(os.name != "nt", reason="Windows must not use os.kill for a lifecycle probe")
def test_windows_owner_probe_does_not_send_a_signal(monkeypatch):
    def unexpected_signal(*_args, **_kwargs):
        raise AssertionError("Windows lifecycle probe must not call os.kill")

    monkeypatch.setattr(os, "kill", unexpected_signal)
    assert RuntimeClaimStore._owner_alive({
        "host": os.environ.get("COMPUTERNAME", ""),
        "pid": os.getpid(),
    }) is True


def test_same_key_race_has_exactly_one_owner(tmp_path):
    store = RuntimeClaimStore(tmp_path)
    # O_EXCL is the cross-process primitive.  A second same-key caller cannot
    # replace the first owner and sees the retained running claim instead.
    first = store.acquire("daily_learning:2026-08-26")
    second = store.acquire("daily_learning:2026-08-26")
    assert first["outcome"] == "acquired"
    assert second["outcome"] == "busy"


def test_different_keys_can_run_independently(tmp_path):
    store = RuntimeClaimStore(tmp_path)
    assert store.acquire("finance_window:2026-08-26:open_validation")["outcome"] == "acquired"
    assert store.acquire("public_sentiment:2026-08-26:open_validation")["outcome"] == "acquired"


def test_completed_claim_returns_immutable_result(tmp_path):
    store = RuntimeClaimStore(tmp_path)
    acquired = store.acquire("daily_learning:2026-08-26")
    assert store.complete(acquired["key"], acquired["claim_token"], {"status": "done"})["outcome"] == "completed"
    repeated = store.acquire("daily_learning:2026-08-26")
    assert repeated == {"outcome": "completed", "key": "daily_learning:2026-08-26", "result": {"status": "done"}}
    repeated["result"]["status"] = "mutated"
    assert store.acquire("daily_learning:2026-08-26")["result"] == {"status": "done"}


def test_dead_or_malformed_claim_requires_recovery_without_auto_retry(tmp_path):
    store = RuntimeClaimStore(tmp_path, owner_alive=lambda _: False)
    acquired = store.acquire("finance_window:2026-08-26:open_validation")
    assert acquired["outcome"] == "acquired"
    assert store.acquire(acquired["key"])["outcome"] == "recovery_required"
    path = next(tmp_path.glob("*.json"))
    path.write_text("{not-json", encoding="utf-8")
    assert store.acquire(acquired["key"])["outcome"] == "recovery_required"


def test_fencing_token_rejects_non_owner_and_result_overwrite(tmp_path):
    store = RuntimeClaimStore(tmp_path)
    acquired = store.acquire("public_sentiment:2026-08-26:open_validation")
    with pytest.raises(PermissionError):
        store.complete(acquired["key"], "wrong-token", {"status": "bad"})
    store.complete(acquired["key"], acquired["claim_token"], {"status": "ok"})
    with pytest.raises(PermissionError):
        store.complete(acquired["key"], "wrong-token", {"status": "overwrite"})
    assert json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))["result"] == {"status": "ok"}


