import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.daily_shift import DailyShift
from core.task import TaskPool


def test_daily_shift_retries_transient_runtime_state_read(monkeypatch, tmp_path):
    state_path = tmp_path / "daemon_state.json"
    state_path.write_text(
        '{"pid":27020,"run_id":"live-run","cycle_progress":{"cycle_status":"completed","stop_reason":"cycle_complete"}}',
        encoding="utf-8",
    )
    original_read_text = Path.read_text
    attempts = {"state": 0}

    def flaky_read_text(path, *args, **kwargs):
        if path == state_path and attempts["state"] == 0:
            attempts["state"] += 1
            raise OSError("simulated atomic-replace sharing violation")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)
    data_dir = tmp_path / "data"
    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data_dir)).build(
        "2026-08-26", daemon_state_path=str(state_path)
    )

    assert report["daemon"]["pid"] == 27020
    assert report["daemon"]["run_id"] == "live-run"
    assert "PID `27020`, run `live-run`" in (data_dir / "daily_shift_latest.md").read_text(encoding="utf-8")



