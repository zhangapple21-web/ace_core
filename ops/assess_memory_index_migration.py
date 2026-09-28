"""评估旧 MemoryIndex 是否适合迁移到 Memory Kernel，不执行迁移。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def assess(source: Path) -> dict:
    if not source.exists():
        return {
            "contract_version": "ace.memory_kernel.migration_assessment.v1",
            "status": "SOURCE_MISSING",
            "source": str(source),
            "execution_authorized": False,
            "production_integration": False,
        }
    data = json.loads(source.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else []
    entries = [item for item in entries if isinstance(item, dict)]
    types = Counter(str(item.get("type") or "UNKNOWN") for item in entries)
    classes = Counter(str(item.get("data_class") or "UNKNOWN") for item in entries)
    with_source = sum(bool(item.get("source_path")) for item in entries)
    total = len(entries)
    decision = "READY_FOR_BOUNDED_MIGRATION"
    reasons = []
    if total > 500:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("legacy_index_large")
    if total and with_source / total < 0.5:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("source_coverage_below_50_percent")
    if classes.get("PRIVATE", 0) == total and total:
        decision = "STAGED_MIGRATION_REQUIRED"
        reasons.append("all_records_private")
    return {
        "contract_version": "ace.memory_kernel.migration_assessment.v1",
        "status": decision,
        "source": str(source),
        "entry_count": total,
        "type_counts": dict(types),
        "data_class_counts": dict(classes),
        "source_path_count": with_source,
        "source_coverage": (with_source / total) if total else 0.0,
        "latest_created_at": max((str(item.get("created_at") or "") for item in entries), default=None),
        "reasons": reasons,
        "action": "只迁移有来源和明确用途的受治理切片；不把日常摘要批量当作事实导入",
        "execution_authorized": False,
        "production_integration": False,
        "promotion": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("06_RUNTIME/ace/data/memory/memory_index.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = assess(args.source)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
