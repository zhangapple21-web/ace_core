"""Run one autonomous free-zone foraging, claim, and execution turn."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.free_zone_autonomy import FreeZoneAutonomy
from core.free_zone_reflection_relay import FreeZoneReflectionRelay
from core.free_zone_loop_status import FreeZoneLoopStatus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(PROJECT_ROOT / "07_SANDBOX" / "free_research"))
    parser.add_argument("--max-experiments", type=int, default=1)
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument(
        "--shift-kind",
        choices=("AD_HOC", "OFF_DUTY"),
        default="AD_HOC",
        help="Record the real sandbox shift context; this never grants production authority.",
    )
    args = parser.parse_args()
    check_in_at = datetime.now(timezone.utc).isoformat()
    report = FreeZoneAutonomy(
        args.root
    ).run_turn(
        max_experiments=args.max_experiments,
        allow_external=args.allow_external,
        execution_context={
            "trigger_kind": "MANUAL_CLI",
            "runner": "ops/run_free_zone_autonomy_turn.py",
            "pid": os.getpid(),
            "shift_kind": args.shift_kind,
            "check_in_at": check_in_at,
        },
    )
    reflection = FreeZoneReflectionRelay(PROJECT_ROOT, sandbox_root=args.root).reflect_available()
    report["ace_reflection"] = reflection
    loop_status = FreeZoneLoopStatus(PROJECT_ROOT)
    report["free_zone_loop_status"] = loop_status.build()
    loop_status.write(report["free_zone_loop_status"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

