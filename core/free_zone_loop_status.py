"""Read-only, per-exchange diagnosis for the ACE Reality <-> Free Zone loop."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FreeZoneLoopStatus:
    def __init__(self, workspace_root: str | Path) -> None:
        self.root = Path(workspace_root).resolve()
        self.exchange_dir = self.root / "08_GOVERNANCE" / "free_zone_exchange" / "receipts"
        self.sandbox = self.root / "07_SANDBOX" / "free_research"
        self.bridge_dir = self.root / "08_GOVERNANCE" / "free_zone_bridge" / "receipts"
        self.runtime = self.root / "06_RUNTIME" / "ace" / "data" / "hourly_task_service_latest.json"

    def build(self, *, relay_result: dict[str, Any] | None = None) -> dict[str, Any]:
        exchanges = {item.get("exchange_id"): item for item in self._values(self.exchange_dir) if item.get("exchange_id")}
        experiments = self._values(self.sandbox / "experiments") + self._values(self.sandbox / "quarantine")
        distillations = self._values(self.sandbox / "distillations")
        bridges = self._values(self.bridge_dir)
        rows = []
        for exchange_id, receipt in sorted(exchanges.items()):
            consumed = [x for x in experiments if self._origin(x) == exchange_id]
            distilled = [x for x in distillations if self._origin(x) == exchange_id]
            reflected = [x for x in bridges if x.get("source", {}).get("origin_reality_gap", {}).get("exchange_id") == exchange_id]
            state = "REFLECTED" if reflected else "DISTILLED" if distilled else "CONSUMED" if consumed else "RELEASED"
            rows.append({"exchange_id": exchange_id, "state": state, "consumed_count": len(consumed), "distilled_count": len(distilled), "reflected_count": len(reflected), "receipt_sha256": receipt.get("receipt_hash")})
        runtime = self._read(self.runtime)
        return {
            "contract_version": "ace.free_zone_loop_status.v1",
            "semantics": "Counts are per hash-bound exchange; historical bridge totals never prove a current bidirectional loop.",
            "runtime_signal": {
                "checked_at": runtime.get("checked_at") if runtime else None,
                "service_status": runtime.get("service_status") if runtime else None,
                "pending_observed": runtime.get("pending_observed") if runtime else None,
                "eligibility": (relay_result or {}).get("status", "UNKNOWN_NOT_RUN"),
                "eligibility_reason": (relay_result or {}).get("reason"),
            },
            "counts": {"released": len(rows), "consumed": sum(x["consumed_count"] > 0 for x in rows), "distilled": sum(x["distilled_count"] > 0 for x in rows), "reflected": sum(x["reflected_count"] > 0 for x in rows)},
            "exchanges": rows,
            "production_integration": False,
        }

    def write(self, status: dict[str, Any]) -> Path:
        path = self.root / "08_GOVERNANCE" / "free_zone_exchange" / "loop_status_latest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _origin(value: dict[str, Any]) -> str | None:
        origin = value.get("origin") if isinstance(value, dict) else None
        if not isinstance(origin, dict):
            origin = value.get("metadata", {}).get("ace_reality_gap_origin") if isinstance(value.get("metadata"), dict) else None
        return origin.get("exchange_id") if isinstance(origin, dict) else None

    def _values(self, directory: Path) -> list[dict[str, Any]]:
        return [value for path in directory.glob("*.json") if (value := self._read(path))]

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None
