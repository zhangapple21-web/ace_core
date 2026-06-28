#!/usr/bin/env python3
"""
ACE 统一状态汇总脚本 (ID-10)

一键输出所有项目运行概况，包括：
  - 系统基本信息（版本、时间、磁盘）
  - 词库/记忆/经验数据量
  - 任务池各状态统计
  - 最近运行摘要
  - 跨智能体学习状态
  - 碎片索引进度

用法：
  python ops/status_summary.py
  python ops/status_summary.py --json    # JSON格式
  python ops/status_summary.py --brief   # 简短模式
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def load_json(path: Path, default=None):
    if not path.is_file():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def count_tasks(state_dir: str) -> int:
    p = BASE_DIR / "task_pool" / state_dir
    if not p.is_dir():
        return 0
    return len(list(p.glob("RQ-*.json")))


def count_knowledge() -> dict:
    kd = BASE_DIR / "09_KNOWLEDGE"
    result = {}
    for cat in ["axiom", "constraint", "pattern", "lesson", "hypothesis"]:
        d = kd / cat
        result[cat] = len(list(d.glob("*.json"))) if d.is_dir() else 0
    return result


def get_lexicon_stats() -> dict:
    lex_path = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
    data = load_json(lex_path, {})
    if not data:
        return {"total_concepts": 0, "total_categories": 0, "categories": {}}
    concepts = data.get("concepts", {})
    categories = data.get("categories", {})
    cat_counts = {}
    if isinstance(concepts, dict):
        for c in concepts.values():
            cat = c.get("category", "待分类") if isinstance(c, dict) else "待分类"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    return {
        "total_concepts": len(concepts) if isinstance(concepts, dict) else 0,
        "total_categories": len(categories) if isinstance(categories, dict) else len(cat_counts),
        "categories": cat_counts,
    }


def get_memory_count() -> int:
    mi_path = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "memory_index.json"
    data = load_json(mi_path, {})
    if isinstance(data, dict):
        if "entries" in data:
            return len(data["entries"])
        return len(data)
    if isinstance(data, list):
        return len(data)
    return 0


def get_daemon_state() -> dict:
    return load_json(
        BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json",
        {},
    )


def get_fragment_index_stats() -> dict:
    fi_path = BASE_DIR / "02_FRAGMENT_INDEX" / "fragment_index.json"
    data = load_json(fi_path, {})
    if not data or not isinstance(data, dict):
        return {"total": 0, "pending_scan": 0, "archaeologized": 0}
    entries = data if "path" not in (list(data.values())[0] if data else {}) else data
    if "entries" in data and isinstance(data["entries"], dict):
        entries = data["entries"]
    total = len(entries) if isinstance(entries, dict) else 0
    archaeologized = 0
    if isinstance(entries, dict):
        for e in entries.values():
            if isinstance(e, dict) and e.get("archaeologized"):
                archaeologized += 1
    pending_scan = total - archaeologized
    return {
        "total": total,
        "pending_scan": pending_scan,
        "archaeologized": archaeologized,
    }


def collect_summary() -> dict:
    import shutil
    total_disk, used_disk, free_disk = shutil.disk_usage(str(BASE_DIR))

    daemon_state = get_daemon_state()
    lex_stats = get_lexicon_stats()
    fi_stats = get_fragment_index_stats()
    knowledge = count_knowledge()

    task_counts = {
        "pending": count_tasks("pending"),
        "active": count_tasks("active"),
        "blocked": count_tasks("blocked"),
        "review": count_tasks("review"),
        "approved": count_tasks("approved"),
        "archived": count_tasks("archived"),
        "rejected": count_tasks("rejected"),
        "graveyard": count_tasks("graveyard"),
    }
    task_total = sum(task_counts.values())

    errors = daemon_state.get("errors", [])
    recent_errors = errors[-10:] if errors else []

    summary = {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "version": load_json(BASE_DIR / "ace_config.json", {}).get("version", "unknown"),
            "base_dir": str(BASE_DIR),
            "disk_free_gb": round(free_disk / (1024 ** 3), 1),
            "disk_free_pct": round(free_disk / total_disk * 100, 1),
            "last_run": daemon_state.get("last_run", "never"),
        },
        "data": {
            "lexicon_concepts": lex_stats.get("total_concepts", 0),
            "lexicon_categories": lex_stats.get("total_categories", 0),
            "memory_index": get_memory_count(),
            "knowledge_total": sum(knowledge.values()),
            "knowledge": knowledge,
            "fragment_index": fi_stats,
        },
        "tasks": {
            "total": task_total,
            "by_state": task_counts,
        },
        "cross_agent": {
            "mine_seed_connected": "mine_seed" in str(daemon_state.get("mining_progress", "")),
            "last_mine_seed_scan": "never",
        },
        "health": {
            "recent_errors_count": len(recent_errors),
            "recent_errors": recent_errors[-5:],
            "active_stale": 0,
        },
    }

    return summary


def print_brief(summary: dict):
    s = summary
    t = s["tasks"]["by_state"]
    k = s["data"]["knowledge"]
    print(
        f"ACE | "
        f"概念:{s['data']['lexicon_concepts']} "
        f"记忆:{s['data']['memory_index']} "
        f"经验:{sum(k.values())} "
        f"任务:{s['tasks']['total']}(P{t['pending']}/A{t['active']}/B{t['blocked']}/R{t['review']}/V{t['archived']}) "
        f"碎片:{s['data']['fragment_index']['total']} "
        f"磁盘:{s['system']['disk_free_gb']}GB"
    )


def print_full(summary: dict):
    s = summary
    print("=" * 65)
    print(f"  ACE 状态汇总  —  {s['timestamp']}")
    print("=" * 65)
    print()

    print("【系统】")
    print(f"  版本:      {s['system']['version']}")
    print(f"  目录:      {s['system']['base_dir']}")
    print(f"  磁盘剩余:  {s['system']['disk_free_gb']} GB ({s['system']['disk_free_pct']}%)")
    print(f"  上次运行:  {s['system']['last_run']}")
    print()

    print("【数据资产】")
    print(f"  词库:      {s['data']['lexicon_concepts']} 个概念 / {s['data']['lexicon_categories']} 个分类")
    print(f"  记忆索引:  {s['data']['memory_index']} 条")
    k = s["data"]["knowledge"]
    print(f"  经验库:    {sum(k.values())} 条  (axiom={k['axiom']}, constraint={k['constraint']}, pattern={k['pattern']}, lesson={k['lesson']})")
    fi = s["data"]["fragment_index"]
    print(f"  碎片索引:  {fi['total']} 个  (已考古 {fi['archaeologized']}, 待处理 {fi['pending_scan']})")
    print()

    print("【任务池】")
    t = s["tasks"]["by_state"]
    print(f"  总计: {s['tasks']['total']} 个")
    print(f"  pending={t['pending']}  active={t['active']}  blocked={t['blocked']}  "
          f"review={t['review']}  approved={t['approved']}  archived={t['archived']}")
    print()

    print("【跨智能体】")
    print(f"  mine-seed: {'已连接' if s['cross_agent']['mine_seed_connected'] else '未连接'}")
    print(f"  上次扫描:  {s['cross_agent']['last_mine_seed_scan']}")
    print()

    if s["health"]["recent_errors_count"] > 0:
        print(f"【健康 - 最近{s['health']['recent_errors_count']}个错误】")
        for e in s["health"]["recent_errors"]:
            print(f"  {e.get('time', '?')} [{e.get('module', '?')}] {e.get('error', '?')}")
        print()

    print("=" * 65)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 状态汇总")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--brief", action="store_true", help="简短单行模式")
    args = parser.parse_args()

    summary = collect_summary()

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    elif args.brief:
        print_brief(summary)
    else:
        print_full(summary)


if __name__ == "__main__":
    main()
