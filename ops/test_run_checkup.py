import pytest

from ops import run_checkup


def test_main_preserves_failed_check_diagnostics_in_snapshot(monkeypatch):
    calls = []
    snapshots = []
    alerts = []
    results = {
        "health_check.py": {
            "success": False,
            "returncode": 2,
            "stdout": "  health output\n",
            "stderr": " health error \n",
            "error": " health failed ",
            "environment": {"API_KEY": "must-not-be-recorded"},
        },
        "status_summary.py": {
            "success": False,
            "returncode": 3,
            "stdout": "  status output  ",
            "stderr": " status error\n",
            "error": " status failed ",
        },
    }

    def fake_run_script(script_name, args=None):
        calls.append((script_name, args))
        if script_name in results:
            return results[script_name]
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(run_checkup, "run_script", fake_run_script)
    monkeypatch.setattr(run_checkup, "write_snapshot", snapshots.append)
    monkeypatch.setattr(
        run_checkup,
        "send_alert",
        lambda level, module, message, notify=False: alerts.append(
            (level, module, message, notify)
        ),
    )
    monkeypatch.setattr(
        run_checkup.sys,
        "argv",
        ["run_checkup.py", "--full", "--quiet"],
    )

    with pytest.raises(SystemExit) as exit_info:
        run_checkup.main()

    assert exit_info.value.code == 2
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["overall"] == "error"
    assert snapshot["checks"]["health"] == {
        "returncode": 2,
        "stdout": "health output",
        "stderr": "health error",
        "error": "health failed",
    }
    assert snapshot["checks"]["status"] == {
        "returncode": 3,
        "stdout": "status output",
        "stderr": "status error",
        "error": "status failed",
    }
    assert "environment" not in snapshot["checks"]["health"]
    assert "must-not-be-recorded" not in str(snapshot)
    assert ("log_rotate.py", []) in calls
    assert alerts == [("error", "checkup", "巡检结果: error", False)]
