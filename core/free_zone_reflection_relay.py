"""Return linked Free Zone results to ACE Reality as shadow research receipts.

The relay is deliberately weaker than acceptance: it translates a completed
Free Zone distillation carrying an ACE-origin receipt into ``MAPPED_SHADOW``.
ACE's independent reviewer must still decide whether any reflection is usable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .free_zone_reality_bridge import FreeZoneRealityBridge


class FreeZoneReflectionRelay:
    def __init__(self, workspace_root: str | Path, *, sandbox_root: str | Path | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox_root = Path(
            sandbox_root or self.workspace_root / "07_SANDBOX" / "free_research"
        ).resolve()
        self.bridge = FreeZoneRealityBridge(self.workspace_root, sandbox_root=self.sandbox_root)

    def reflect_available(self) -> dict[str, Any]:
        reflected = []
        skipped = 0
        for source in sorted((self.sandbox_root / "distillations").glob("*.json")):
            value = self._read(source)
            if not isinstance(value, dict) or not isinstance(value.get("origin"), dict):
                skipped += 1
                continue
            origin = value["origin"]
            exchange_id = origin.get("exchange_id")
            receipt_sha256 = origin.get("receipt_sha256")
            if not isinstance(exchange_id, str) or not isinstance(receipt_sha256, str):
                skipped += 1
                continue
            incoming = self.workspace_root / "08_GOVERNANCE" / "free_zone_exchange" / "receipts" / f"{exchange_id}.json"
            if not incoming.is_file():
                skipped += 1
                continue
            try:
                receipt = self.bridge.build(source, self._mapping(source, value, incoming))
            except ValueError:
                # One malformed or stale historical artifact must not hide
                # later valid reflections in the same Free Zone turn.
                skipped += 1
                continue
            reflected.append({
                "experiment_id": value.get("experiment_id"),
                "bridge_id": receipt.get("bridge_id"),
                "status": receipt.get("disposition", {}).get("status"),
                "origin_exchange_id": exchange_id,
            })
        return {
            "status": "REFLECTIONS_RECORDED" if reflected else "NO_LINKED_FREE_ZONE_RESULT",
            "reflected_count": len(reflected),
            "skipped_count": skipped,
            "reflections": reflected,
            "task_created": False,
            "model_call": False,
            "production_runtime_mutation": False,
        }

    def _mapping(self, source: Path, distillation: dict[str, Any], incoming: Path) -> dict[str, Any]:
        experiment_id = str(distillation.get("experiment_id", "UNKNOWN"))
        outcome = str(distillation.get("outcome", "UNKNOWN"))
        relative_source = source.relative_to(self.workspace_root).as_posix()
        relative_incoming = incoming.relative_to(self.workspace_root).as_posix()
        return {
            "mapping_id": f"FREE-ZONE-REFLECTION-{experiment_id}",
            "epistemic_status": "INFERENCE",
            "observation": f"Free Zone experiment {experiment_id} returned {outcome} for a linked ACE Reality gap.",
            "learning": "The result is preserved as a shadow reflection; it is not accepted knowledge or a production fact.",
            "reality_scope": "ACE Reality research observation",
            "research_question": "What independent ACE-side evidence would confirm, refine, or reject this reflected Free Zone result?",
            "expected_result": "One hash-bound shadow receipt preserves both directional lineage without changing ACE authority.",
            "verification_method": "Verify distillation, incoming exchange, source hashes, and zero TaskPool or production mutation.",
            "constraints": [
                "shadow research receipt only",
                "no automatic acceptance",
                "no TaskPool creation",
                "no production runtime mutation",
            ],
            "evidence_refs": [
                {"ref": relative_source, "independence_group": "free_zone_distillation", "kind": "sandbox_distillation"},
                {"ref": relative_incoming, "independence_group": "ace_reality_gap", "kind": "incoming_exchange"},
            ],
            "ace_review": {
                "decision": "HOLD_FOR_EVIDENCE",
                "reviewer": "free_zone_reflection_relay",
                "review_basis": ["linked Free Zone distillation", "bound ACE Reality exchange receipt", "no automatic acceptance"],
            },
        }

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None
