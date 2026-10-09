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


def _run_main_with(monkeypatch, health_result):
    import json as _json

    snapshots = []
    alerts = []

    def fake_run_script(script_name, args=None):
        if script_name == "health_check.py":
            return health_result
        if script_name == "status_summary.py":
            return {"success": True, "returncode": 0, "stdout": _json.dumps({
                "data": {"lexicon_concepts": 1, "memory_index": 1, "knowledge": {"a": 1}},
                "tasks": {"total": 1},
                "system": {"disk_free_gb": 50.0},
            }), "stderr": ""}
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
    monkeypatch.setattr(run_checkup.sys, "argv", ["run_checkup.py", "--quiet"])
    return snapshots, alerts


def test_warning_json_is_not_promoted_to_error(monkeypatch):
    """rc=1 carries a valid warning report: trust it, don't force error."""
    import json as _json

    report = {
        "overall": "warning", "passed": 18, "warnings": 2, "errors": 0,
        "checks": [
            {"name": "ok_probe", "passed": True, "severity": "error", "detail": "x"},
            {"name": "known_backlog", "passed": False, "severity": "warning", "detail": "62 known"},
            {"name": "stale_ratings", "passed": False, "severity": "warning", "detail": "STALE=3"},
        ],
    }
    snapshots, alerts = _run_main_with(monkeypatch, {
        "success": False, "returncode": 1,
        "stdout": _json.dumps(report, ensure_ascii=False), "stderr": "",
    })

    with __import__("pytest").raises(SystemExit) as exit_info:
        run_checkup.main()
    assert exit_info.value.code == 1
    snapshot = snapshots[0]
    assert snapshot["overall"] == "warning"
    health = snapshot["checks"]["health"]
    assert health["overall"] == "warning"
    assert health["returncode"] == 1
    assert {item["name"] for item in health["failed_checks"]} == {
        "known_backlog", "stale_ratings",
    }
    assert alerts == [("warn", "checkup", "健康检查警告: 2个警告", False),
                      ("warn", "checkup", "巡检结果: warning", False)]


def test_error_json_keeps_failed_probe_identity(monkeypatch):
    """rc=2 with a valid error report stays error AND names its probes."""
    import json as _json

    report = {
        "overall": "error", "passed": 17, "warnings": 0, "errors": 1,
        "checks": [
            {"name": "daemon_beat", "passed": False, "severity": "error", "detail": "stale 2h"},
        ],
    }
    snapshots, alerts = _run_main_with(monkeypatch, {
        "success": False, "returncode": 2,
        "stdout": _json.dumps(report, ensure_ascii=False), "stderr": "",
    })

    with __import__("pytest").raises(SystemExit) as exit_info:
        run_checkup.main()
    assert exit_info.value.code == 2
    snapshot = snapshots[0]
    assert snapshot["overall"] == "error"
    assert snapshot["checks"]["health"]["failed_checks"] == [
        {"name": "daemon_beat", "severity": "error"},
    ]
    assert alerts[0][0] == "error"
