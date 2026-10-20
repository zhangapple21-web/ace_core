#!/usr/bin/env python3
"""只读对账器：任务账本能不能复现每个计数器当前值。

这是 C4（带活指针与操作后快照的可重放账本）的检查面。命令本身不打开任何
TaskPool 写口，不改任何任务文件；输出是可审计的 JSON 报表。

跑法：
    cd C:/tmp/ace_core
    PYTHONIOENCODING=utf-8 py -3.11 ops/task_ledger_reconcile.py
    PYTHONIOENCODING=utf-8 py -3.11 ops/task_ledger_reconcile.py --limit 2000 --show 5

退出码：0 = 账实相符（无 chain break、无未配平 hold）；1 = 有硬伤；2 = 参数/读取错误。
未种基线的存量任务只计入 unaudited_legacy，不算硬伤（它们还没有账）。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import task_ledger as ledger  # noqa: E402
from core.task import Task  # noqa: E402


def _records(pool_dir: Path, limit: int) -> list[Path]:
    files = sorted(pool_dir.glob("*/*.json"))
    return files[:limit] if limit else files


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only task ledger reconciliation.")
    parser.add_argument("--pool", default=str(ROOT / "task_pool"), help="TaskPool directory")
    parser.add_argument("--limit", type=int, default=0, help="Max task files to read (0 = all)")
    parser.add_argument("--show", type=int, default=3, help="How many offending task ids to list")
    parser.add_argument("--full-report", action="store_true", help="Include per-kind row counts")
    args = parser.parse_args()

    pool_dir = Path(args.pool)
    if not pool_dir.is_dir():
        print(json.dumps({"error": f"pool_dir_absent:{pool_dir}"}, ensure_ascii=False))
        return 2

    kinds: Counter[str] = Counter()
    counters_drifted: Counter[str] = Counter()
    stats = {
        "pool": str(pool_dir),
        "tasks_read": 0,
        "unreadable": 0,
        "with_ledger": 0,
        "unaudited_legacy": 0,
        "clean": 0,
        "chain_break_tasks": 0,
        "reconcile_mismatch_tasks": 0,
        "unclosed_hold_tasks": 0,
        "dead_ref_rows": 0,
    }
    offenders: dict[str, dict] = {}

    for path in _records(pool_dir, args.limit):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            task = Task.from_dict(record)
        except (OSError, ValueError):
            stats["unreadable"] += 1
            continue
        stats["tasks_read"] += 1
        rows = record.get("ledger") or []
        if not rows:
            stats["unaudited_legacy"] += 1
            continue
        stats["with_ledger"] += 1
        for row in rows:
            kind = str(row.get("kind") or "?")
            kinds[kind] += 1
            ok, _error = ledger.resolve_ref(row.get("ref") or {}, pool_dir=pool_dir)
            if not ok:
                stats["dead_ref_rows"] += 1
                offenders.setdefault(task.task_id, {})["dead_ref"] = _error
        chain = ledger.verify_chain(task)
        if chain:
            stats["chain_break_tasks"] += 1
            offenders.setdefault(task.task_id, {})["chain_break"] = chain[:3]
        drift = ledger.reconcile(task)
        if drift:
            stats["reconcile_mismatch_tasks"] += 1
            for name in drift:
                counters_drifted[name] += 1
            offenders.setdefault(task.task_id, {})["drift"] = drift
        holds = ledger.unclosed_holds(task)
        if holds:
            stats["unclosed_hold_tasks"] += 1
            offenders.setdefault(task.task_id, {})["unclosed_holds"] = len(holds)
        if not chain and not drift and not holds:
            stats["clean"] += 1

    stats["ledger_row_kinds"] = dict(kinds) if args.full_report else {k: kinds[k] for k in sorted(kinds)}
    stats["drift_by_counter"] = dict(counters_drifted)
    stats["offenders_sample"] = dict(list(offenders.items())[: max(0, args.show)])
    stats["offender_total"] = len(offenders)
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    hard = stats["chain_break_tasks"] + stats["unclosed_hold_tasks"] + stats["reconcile_mismatch_tasks"] + stats["dead_ref_rows"]
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
