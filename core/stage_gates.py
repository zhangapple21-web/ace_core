"""Gate telemetry: every gated routine says which gate held it.

A stage that silently skips looks identical to a stage with nothing to do.
This module gives all of them one shared vocabulary for reporting their
gate evaluation into runtime state. Read-only bookkeeping: it never
decides, never schedules, never writes tasks. Downstream (observer rules,
patrol inventory) reads the recorded decisions; the nine-day silent shift
is the reason this exists.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Mapping, Tuple

STATE_KEY = "stage_gate_decisions"


def evaluate_gates(gates: Mapping[str, Tuple[bool, str]]) -> Tuple[bool, str]:
    """Combine named gate checks into one decision.

    Each gate is (passed, detail). All must pass. Returns
    (all_passed, blocking_gate_name or "GO").
    """
    for name, (passed, _) in gates.items():
        if not passed:
            return False, str(name)
    return True, "GO"


def record_gate(
    state: Dict[str, Any],
    stage: str,
    gates: Mapping[str, Tuple[bool, str]],
    decision: str,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Record one gate evaluation into runtime state. Returns the record."""
    now = datetime.now()
    record: Dict[str, Any] = {
        "at": now.isoformat(),
        "decision": decision,
        "gates": {
            name: {"passed": bool(passed), "detail": str(detail)}
            for name, (passed, detail) in gates.items()
        },
    }
    if extra:
        for key, value in extra.items():
            record[str(key)] = value
    states = state.get(STATE_KEY)
    if not isinstance(states, dict):
        states = {}
        state[STATE_KEY] = states
    states[str(stage)] = record
    return record


__all__ = ["STATE_KEY", "evaluate_gates", "record_gate"]
