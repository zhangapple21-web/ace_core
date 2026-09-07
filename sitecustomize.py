"""Automatic continuation-gate inheritance for every Python entrypoint."""
from __future__ import annotations

import sys
from pathlib import Path

_workspace = Path(__file__).resolve().parents[1]
if str(_workspace) not in sys.path:
    sys.path.insert(0, str(_workspace))
try:
    import continue_gate_runtime
    continue_gate_runtime.install()
except Exception:
    # Never hide the original script error; the ACE daemon still performs its
    # explicit boundary check and writes a durable handoff receipt.
    pass
