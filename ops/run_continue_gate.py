#!/usr/bin/env python3
"""Evaluate the fail-closed continue-before-work contract from JSON files."""

import argparse
import json
from pathlib import Path

from core.continue_gate import evaluate_continue_gate


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_continue_gate(_load(args.context), _load(args.protocol), _load(args.evidence))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "CONTINUE" else 2


if __name__ == "__main__":
    raise SystemExit(main())

