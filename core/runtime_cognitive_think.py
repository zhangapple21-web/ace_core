"""Publish the cognitive-think gate at the daemon boundary.

This adapter does not call models and does not grant production authority.
It records the default think/judgment/execute split so later processes can
recover the same decision from disk instead of session memory.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.cognitive_think_gate import (
    CHARTER,
    COGNITIVE_HUB,
    CONTRACT_VERSION,
    evaluate_cognitive_think_gate,
)


def evaluate_daemon_cognitive_think(
    base_dir: Path,
    state: dict[str, Any],
    config: dict[str, Any],
    run_id: str,
    continue_status: str = "CONTINUE",
) -> dict[str, Any]:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime", {}), dict) else {}
    actor_role = str(
        state.get("cognitive_actor_role")
        or runtime.get("cognitive_actor_role")
        or COGNITIVE_HUB
    )
    sediment = state.get("cognitive_sediment")
    if not isinstance(sediment, dict):
        sediment = {}
    decision = evaluate_cognitive_think_gate(
        actor_role=actor_role,
        unknown_count=state.get("cognitive_unknown_count", 0) if isinstance(state.get("cognitive_unknown_count", 0), int) else 0,
        think_rounds=state.get("cognitive_think_rounds", 0) if isinstance(state.get("cognitive_think_rounds", 0), int) else 0,
        new_evidence_since_last_think=state.get("cognitive_new_evidence", False) is True,
        judgment_formed=state.get("cognitive_judgment_formed", False) is True,
        judgment_changes_future_behavior=state.get("cognitive_judgment_changes_future", False) is True,
        sediment=sediment,
        execution_requested=state.get("cognitive_execution_requested", False) is True,
        existing_execution_authorized=continue_status == "CONTINUE",
        human_decision_required=state.get("cognitive_needs_human", False) is True,
        complexity=str(state.get("cognitive_complexity") or runtime.get("cognitive_complexity") or "medium"),
    )
    decision["scope"] = "ace_daemon_cycle"
    decision["run_id"] = run_id
    decision["continue_status"] = continue_status
    runtime_dir = Path(base_dir) / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "ace.cognitive_think.runtime_state.v1",
        "contract_version": CONTRACT_VERSION,
        "charter": CHARTER,
        "run_id": run_id,
        "decision": decision,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = runtime_dir / "cognitive_think_runtime_state.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    decision["runtime_state_path"] = str(path)
    return decision


__all__ = ["evaluate_daemon_cognitive_think"]
