"""Process-wide fail-closed continuation gate installation."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

_INSTALLED = False
_ALLOWED = True
_STATE_PATH = None
_CONTEXT_ID = ""


def is_ace_daemon_serve(argv=None):
    args = list(sys.argv if argv is None else argv)
    return len(args) >= 3 and Path(args[0]).name == "ace.py" and args[1:3] == ["daemon", "--serve"]


def _state_path():
    return Path(os.environ.get("CONTINUE_GATE_STATE", Path.cwd() / "runtime" / "continue_gate_runtime_state.json"))


def _write_receipt(state_path, reason):
    receipt = state_path.with_name("continue_gate_runtime_receipts.jsonl")
    row = {"receipt_id": f"runtime-{uuid.uuid4().hex}", "status": "HANDOFF_REQUIRED", "reason": reason}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _blocked_connect(sock, address):
    raise RuntimeError("continue_gate CLOSED_AND_HANDOFF")


def install():
    global _INSTALLED, _ALLOWED, _STATE_PATH, _CONTEXT_ID
    if _INSTALLED:
        return _ALLOWED
    _INSTALLED = True
    _STATE_PATH = _state_path()
    if os.environ.get("CONTINUE_GATE_BYPASS") == "1":
        return True
    try:
        state = json.loads(_STATE_PATH.read_text(encoding="utf-8")) if _STATE_PATH.is_file() else {}
    except Exception:
        state = {}
    if is_ace_daemon_serve():
        old = state.get("context_id", "")
        _CONTEXT_ID = f"daemon-serve-{uuid.uuid4().hex[:12]}"
        state.update({"handoff_required": False, "bootstrap": "ace_daemon_serve_fresh_process", "context_id": _CONTEXT_ID, "replaces_context_id": old})
        _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    if state.get("handoff_required") is True or state.get("prior_attempt_without_receipt") is True:
        _ALLOWED = False
        _write_receipt(_STATE_PATH, "CLOSED_AND_HANDOFF")
        import socket
        socket.socket.connect = _blocked_connect
        print("continue_gate CLOSED_AND_HANDOFF", file=sys.stderr)
    return _ALLOWED


__all__ = ["install", "is_ace_daemon_serve"]
