#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import continue_gate_runtime as cgr


def test_is_ace_daemon_serve_only_matches_long_labor_boot():
    assert cgr.is_ace_daemon_serve([r"C:\tmp\ace_core\ace.py", "daemon", "--serve"]) is True
    assert cgr.is_ace_daemon_serve([r"C:\tmp\ace_core\ace.py", "daemon", "--serve", "--interval", "300"]) is True
    assert cgr.is_ace_daemon_serve([r"C:\tmp\ace_core\ace.py", "daemon"]) is False
    assert cgr.is_ace_daemon_serve([r"C:\tmp\ace_core\ops\test_ds41_long_labor.py"]) is False


def _reset(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(cgr, "_INSTALLED", False)
    monkeypatch.setattr(cgr, "_ALLOWED", True)
    monkeypatch.setattr(cgr, "_STATE_PATH", None)
    monkeypatch.setattr(cgr, "_CONTEXT_ID", "")
    monkeypatch.setattr(sys, "argv", argv)
    state_path = tmp_path / "continue_gate_runtime_state.json"
    monkeypatch.setenv("CONTINUE_GATE_STATE", str(state_path))
    monkeypatch.delenv("CONTINUE_GATE_BYPASS", raising=False)
    return state_path


def test_daemon_serve_install_opens_fresh_context(monkeypatch, tmp_path):
    state_path = _reset(monkeypatch, tmp_path, [r"C:\tmp\ace_core\ace.py", "daemon", "--serve"])
    state_path.write_text(json.dumps({
        "schema": "continue_before_work.runtime_state.v1",
        "context_id": "stale-ctx",
        "handoff_required": True,
        "prior_attempt_without_receipt": False,
        "failure_count": 1,
    }), encoding="utf-8")
    allowed = cgr.install()
    assert allowed is True
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["handoff_required"] is False
    assert state["bootstrap"] == "ace_daemon_serve_fresh_process"
    assert state["context_id"].startswith("daemon-serve-")
    assert state["replaces_context_id"] == "stale-ctx"


def test_other_scripts_do_not_clear_handoff_latch(monkeypatch, tmp_path):
    state_path = _reset(monkeypatch, tmp_path, [r"C:\tmp\ace_core\ops\probe.py"])
    state_path.write_text(json.dumps({
        "schema": "continue_before_work.runtime_state.v1",
        "context_id": "stale-ctx",
        "handoff_required": True,
        "prior_attempt_without_receipt": False,
        "failure_count": 0,
    }), encoding="utf-8")
    allowed = cgr.install()
    assert allowed is False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["handoff_required"] is True
    assert state.get("bootstrap") != "ace_daemon_serve_fresh_process"
