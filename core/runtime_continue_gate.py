"""Runtime boundary for fail-closed continuation decisions.

This adapter makes ``continue_gate`` executable at the daemon boundary.  It
does not call providers; it only evaluates local evidence and records a
handoff receipt when continuation is unsafe.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.continue_gate import CLOSE_AND_HANDOFF, evaluate_continue_gate


def evaluate_daemon_boundary(base_dir: Path, state: dict[str, Any], config: dict[str, Any], run_id: str) -> dict[str, Any]:
    runtime = config.get("runtime", {}) if isinstance(config.get("runtime", {}), dict) else {}
    context_limit = runtime.get("context_limit_tokens", 200_000)
    estimated = state.get("context_estimated_tokens", 0)
    context = {
        "fresh": state.get("continuation_context_fresh", True) is True,
        "context_id": run_id or state.get("run_id") or f"ace-{uuid.uuid4().hex[:12]}",
        "estimated_tokens": estimated if isinstance(estimated, (int, float)) else 0,
        "context_limit": context_limit if isinstance(context_limit, (int, float)) else 200_000,
        "same_failure_count": state.get("continue_gate_failure_count", 0),
        "prior_attempt_without_receipt": state.get("continue_gate_prior_attempt_without_receipt", False) is True,
    }
    protocol = {
        "available": state.get("continue_gate_protocol_available", True) is True,
        "provider": str(state.get("continue_gate_provider") or runtime.get("continue_gate_provider") or "ace-local"),
        "interface": str(state.get("continue_gate_interface") or runtime.get("continue_gate_interface") or "daemon-cycle"),
        "continuation_supported": state.get("continue_gate_continuation_supported", True) is True,
        "provider_degraded": state.get("continue_gate_provider_degraded", False) is True,
        "fallbacks_configured": state.get("continue_gate_fallbacks_configured", True) is True,
    }
    evidence = {"required_receipts": [], "receipts": []}
    decision = evaluate_continue_gate(context, protocol, evidence)
    decision["scope"] = "ace_daemon_cycle"
    decision.update(
        {
            "context_id": context["context_id"],
            "provider": protocol["provider"],
            "interface": protocol["interface"],
            "prior_attempt_status": (
                "NO_RECEIPT" if context["prior_attempt_without_receipt"] else "PASS"
            ),
            "next_context_required": decision["status"] == CLOSE_AND_HANDOFF,
        }
    )
    if decision["status"] == CLOSE_AND_HANDOFF:
        receipt_dir = base_dir / "runtime" / "continue_gate_receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt = {
            "receipt_id": f"continue-gate-{uuid.uuid4().hex}",
            "schema": "continue_before_work.receipt.v1",
            "status": "HANDOFF_REQUIRED",
            "decision": decision,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = receipt_dir / f"{receipt['receipt_id']}.json"
        path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        decision["receipt_path"] = str(path)
    # Publish the latest boundary to the shared process guard.  Any future
    # Python entrypoint in this checkout inherits the same decision through
    # ``sitecustomize`` without having to call this function itself.
    runtime_dir = base_dir / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    shared_state = runtime_dir / "continue_gate_runtime_state.json"
    shared_state.write_text(
        json.dumps(
            {
                "schema": "continue_before_work.runtime_state.v1",
                "context_id": context["context_id"],
                "handoff_required": decision["status"] == CLOSE_AND_HANDOFF,
                "prior_attempt_without_receipt": context["prior_attempt_without_receipt"],
                "failure_count": context["same_failure_count"],
                "last_decision": decision,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return decision


__all__ = ["evaluate_daemon_boundary"]
