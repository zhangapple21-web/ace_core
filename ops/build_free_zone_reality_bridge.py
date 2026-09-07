#!/usr/bin/env python3
"""Build one explicit Free Zone -> ACE reality research receipt.

This command is intentionally manual.  It does not scan for candidates, create
TaskPool work, call a model, touch the daemon, or invoke ACE Admission.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.free_zone_reality_bridge import FreeZoneRealityBridge


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="ACE workspace root")
    parser.add_argument("--source", required=True, help="one named Free Zone distillation JSON")
    parser.add_argument("--mapping", required=True, help="explicit ACE-side mapping JSON")
    parser.add_argument("--receipt-dir", help="optional ACE-side receipt directory")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    source = _resolve(root, args.source)
    mapping_path = _resolve(root, args.mapping)
    try:
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"mapping is unreadable: {error.__class__.__name__}") from error
    if not isinstance(mapping, dict):
        raise SystemExit("mapping must be a JSON object")

    bridge = FreeZoneRealityBridge(
        root,
        receipt_dir=_resolve(root, args.receipt_dir) if args.receipt_dir else None,
    )
    receipt = bridge.build(source, mapping)
    summary = {
        "bridge_id": receipt["bridge_id"],
        "status": receipt["disposition"]["status"],
        "receipt": bridge.receipt_path(receipt["bridge_id"]).relative_to(root).as_posix(),
        "source_experiment_id": receipt["source"]["experiment_id"],
        "independent_count": receipt["evidence"]["independent_count"],
        "task_created": receipt["disposition"]["task_created"],
        "model_call": receipt["disposition"]["model_call"],
        "production_runtime_mutation": receipt["disposition"]["production_runtime_mutation"],
        "admission_bypassed": receipt["disposition"]["admission_bypassed"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

