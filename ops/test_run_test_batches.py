import json
from pathlib import Path

import pytest

import ops.run_test_batches as batches


def test_keyboard_interrupt_persists_partial_batch_summary(monkeypatch, tmp_path):
    monkeypatch.setattr(batches, "OUT", tmp_path)
    monkeypatch.setattr(batches, "ROOT", tmp_path)
    ops_dir = tmp_path / "ops"
    ops_dir.mkdir()
    (ops_dir / "test_first.py").write_text("", encoding="utf-8")
    (ops_dir / "test_second.py").write_text("", encoding="utf-8")
    calls = 0

    def interrupted_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    monkeypatch.setattr(batches.subprocess, "run", interrupted_run)
    monkeypatch.setattr("sys.argv", ["run_test_batches.py", "--batch-size", "1"])

    assert batches.main() == 130
    summary = json.loads((tmp_path / "batch_summary_20260831.json").read_text(encoding="utf-8"))
    assert summary["interrupted"] is True
    assert summary["completed"] == 1
    assert summary["failed"] == 0
    assert (tmp_path / "batch_01.json").exists()


