#!/usr/bin/env python3
"""Print a read-only, evidence-first MinerPool resident atlas.

Usage:
  python ops/miner_pool_resident_atlas.py
  python ops/miner_pool_resident_atlas.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.miner_pool.resident_atlas import collect_resident_atlas


def print_text(atlas: dict) -> None:
    summary = atlas["summary"]
    print(
        "MinerPool resident atlas: "
        f"{summary['resident_count']} residents; "
        f"{summary['shadow_evaluation']} shadow; "
        f"{summary['unregistered_profile_reference']} profile references needing evidence; "
        f"{summary['verified_production_eligible']} production-eligible."
    )
    for resident in atlas["residents"]:
        execution = resident["execution"]
        safe_room = resident["safe_room"]["room"]
        print(
            f"- {resident['resident_id']}: {resident['catalog_state']} / "
            f"{resident['routing_eligibility']} / {safe_room} | profiles={','.join(resident['profile_references']) or '-'} | "
            f"calls={execution['attempted']} ok={execution['successful']} fail={execution['failed']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only ACE MinerPool resident atlas")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help="ACE root")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    atlas = collect_resident_atlas(args.root)
    if args.json:
        print(json.dumps(atlas, ensure_ascii=False, indent=2))
    else:
        print_text(atlas)


if __name__ == "__main__":
    main()
