"""Print a read-only evidence relevance audit for persisted TaskPool JSON."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.evidence_relevance_shadow import shadow_audit


def load_tasks(pool_dir):
    tasks = []
    for path in sorted(Path(pool_dir).rglob("RQ-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            tasks.append(value)
    return tuple(tasks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pool_dir")
    parser.add_argument("start_at")
    parser.add_argument("end_at")
    arguments = parser.parse_args()
    report = shadow_audit(
        load_tasks(arguments.pool_dir),
        start_at=arguments.start_at,
        end_at=arguments.end_at,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
