"""Run one bounded R1/R2 archaeology pulse inside the free-research sandbox."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.museum_archaeology_inventory import MuseumArchaeologyInventory


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_turn(*, sandbox_root: str | Path, history_root: str | Path) -> dict[str, Any]:
    """Inventory museum material and publish at most one inbound-food record.

    Museum archaeology is a food source, not a hidden free-zone executor.  It
    never creates an experiment, distillation, proposal, or Court decision.
    When its immutable inventory changes, it writes one traceable food record
    to the sandbox inbox.  ``FreeZoneAutonomy`` subsequently decides whether
    to claim and execute the material without a teacher or Court pre-check.
    """

    root = Path(sandbox_root).resolve()
    reports = root / "reports"
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)

    inventory = MuseumArchaeologyInventory(history_root).scan()
    current_hash = inventory["inventory_sha256"]
    state_path = reports / "museum_archaeology_state.json"
    prior: dict[str, Any] = {}
    if state_path.exists():
        try:
            prior = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            prior = {}

    event = "NO_NEW_MUSEUM_WORK"
    food_path: Path | None = None
    if prior.get("inventory_sha256") != current_hash:
        daily_reports = inventory["summary"]["historical_daily_report_count"]
        adaptable = [
            artifact["artifact_id"]
            for artifact in inventory["artifacts"]
            if artifact["present"] and artifact["disposition"] in {"ABSORB", "ADAPT"}
        ]
        if daily_reports >= 7 and adaptable:
            food_path = inbox / f"museum_continuity_{current_hash[:12]}.json"
            _atomic_write(food_path, {
                "food_kind": "museum_history",
                "hypothesis": (
                    "A verified historical daily-report series can justify a bounded, local "
                    "museum-observation pulse without reviving any historical runtime."
                ),
                "method": (
                    "Re-check the retained allow-listed inventory, its hash, report-series count, "
                    "and explicit non-actions as an isolated free-zone historical probe."
                ),
                "inventory_sha256": current_hash,
                "inventory_contract": inventory["contract_version"],
                "historical_daily_report_count": daily_reports,
                "adaptable_artifact_ids": adaptable,
                "inventory_report": str(reports / f"museum_archaeology_inventory_{current_hash[:12]}.json"),
                "non_actions": inventory["explicit_non_actions"],
                "mode": "FREE_RESEARCH_ONLY",
                "production_integration": False,
            })
            event = "MUSEUM_FOOD_RECORDED"
        else:
            event = "MUSEUM_EVIDENCE_INSUFFICIENT"

    generated_at = datetime.now(timezone.utc).isoformat()
    report = {
        "contract_version": "ace.museum_archaeology_turn.v1",
        "mode": "FREE_RESEARCH_ONLY",
        "generated_at": generated_at,
        "event": event,
        "food_path": str(food_path) if food_path else None,
        "inventory_sha256": current_hash,
        "inventory_summary": inventory["summary"],
        "court_status": "DEFERRED_TO_OUTBOUND_DISTILLATION",
        "teacher_queue_count": None,
        "museum_role": "INBOUND_FOOD_ONLY",
        "production_integration": False,
    }
    _atomic_write(reports / "museum_archaeology_latest.json", report)
    _atomic_write(state_path, {"inventory_sha256": current_hash, "last_event": event, "updated_at": generated_at})
    _atomic_write(reports / f"museum_archaeology_inventory_{current_hash[:12]}.json", inventory)
    (reports / f"museum_archaeology_inventory_{current_hash[:12]}.md").write_text(
        MuseumArchaeologyInventory.render_markdown(inventory), encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT / "07_SANDBOX" / "free_research"))
    parser.add_argument("--history-root", default=str(PROJECT_ROOT.parent))
    args = parser.parse_args()
    print(json.dumps(run_turn(sandbox_root=args.root, history_root=args.history_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

