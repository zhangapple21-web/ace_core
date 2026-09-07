"""Release a narrowly defined, observed ACE runtime gap as Free Zone food.

This is intentionally a detector, not a scheduler or a second TaskPool.  Its
sole currently-supported signal is an existing lifecycle report that says
claimable work was present but the sole daemon did not service it.  Two
independent runtime artifacts are retained before the gap can enter the Free
Zone, and a normal no-signal result creates nothing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .reality_free_zone_exchange import RealityFreeZoneExchange


class RealityGapRelay:
    """Read ACE runtime evidence and release only a qualified backlog gap."""

    def __init__(self, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.runtime_dir = self.workspace_root / "06_RUNTIME" / "ace" / "data"
        self.memory_dir = self.runtime_dir / "memory"
        self.exchange = RealityFreeZoneExchange(self.workspace_root)

    def scan_and_release(self) -> dict[str, Any]:
        hourly = self.runtime_dir / "hourly_task_service_latest.json"
        daemon_state = self.memory_dir / "daemon_state.json"
        report = self._read(hourly)
        state = self._read(daemon_state)
        if not isinstance(report, dict) or not isinstance(state, dict):
            return self._no_candidate("runtime_evidence_unavailable")
        if report.get("service_status") != "ELIGIBLE_WORK_NOT_SERVICED":
            return self._no_candidate("no_unserviced_claimable_work")
        if not isinstance(report.get("pending_observed"), int) or report["pending_observed"] <= 0:
            return self._no_candidate("pending_count_not_a_positive_integer")
        execution = report.get("execution_evidence")
        if not isinstance(execution, dict) or execution.get("status") != "DAEMON_CONTEXT_BOUND":
            return self._no_candidate("daemon_execution_not_attributed")
        receipt = self.exchange.release({
            "gap_id": f"ACE-GAP-UNSERVICED-{report.get('hour', 'UNKNOWN')}",
            "epistemic_status": "FACT",
            "observation": (
                f"The existing daemon lifecycle reported {report['pending_observed']} claimable item(s) "
                "but did not service them in the recorded hour."
            ),
            "reality_scope": "existing ACE TaskPool lifecycle service",
            "research_question": "Which bounded counterexample explains the unserviced claimable backlog without changing lifecycle authority?",
            "expected_result": "A Free Zone probe retains a falsifiable explanation or counterexample while ACE lifecycle ownership remains unchanged.",
            "verification_method": "Recheck the bound hourly report and daemon state hashes; verify zero TaskPool, routing, model, or production mutation by this relay.",
            "constraints": [
                "no TaskPool creation",
                "no model call",
                "no production runtime mutation",
                "existing Admission, Validator, Data, Risk, and Finance gates remain authoritative",
            ],
            "evidence_refs": [
                {"ref": hourly.relative_to(self.workspace_root).as_posix(), "independence_group": "task_lifecycle_report", "kind": "runtime_report"},
                {"ref": daemon_state.relative_to(self.workspace_root).as_posix(), "independence_group": "daemon_state", "kind": "runtime_state"},
            ],
            "ace_review": {
                "decision": "RELEASE_TO_FREE_ZONE",
                "reviewer": "ace_reality_runtime_relay",
                "review_basis": ["positive unserviced claimable count", "attributed sole-daemon lifecycle report", "separate daemon state snapshot"],
            },
        })
        return {"status": "RELEASED_TO_FREE_ZONE", "receipt": receipt, "task_created": False, "model_call": False}

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _no_candidate(reason: str) -> dict[str, Any]:
        return {
            "status": "NO_ELIGIBLE_REALITY_GAP",
            "reason": reason,
            "task_created": False,
            "model_call": False,
            "production_runtime_mutation": False,
        }
