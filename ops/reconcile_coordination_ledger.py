"""Apply explicit acceptance-audit transitions to one durable ledger."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent_team.coordination_ledger import reconcile_directory

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    changes = reconcile_directory(args.root, write=not args.dry_run)
    print(json.dumps({"changes": changes, "written": not args.dry_run and bool(changes)}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())


