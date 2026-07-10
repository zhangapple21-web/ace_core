#!/usr/bin/env python3
"""
Environment First Protocol (EFP) - 环境优先协议
================================================

公理根基:
  #002 考古不是搬家是炼金 (读->蒸馏->存原则, 原始笔记不存档)
  #010 演化只允许增加结构, 不允许破坏不变量
  #011 记忆是推断的不是存储的
  #021 贡献不可回收, 共享知识一旦入池不可单方撤回

执行语义:
  任何新环境启动时, 第一件事不是问用户, 而是先理解自己身处什么环境.
  行为协议, 不是语言能力. 一旦环境内出现 backup/README/seed/snapshot/
  archive/part*/recovery 等关键词, 协议立即触发, 不等待用户授权.

协议七步:
  1. 扫描工作目录
  2. 建立资产索引
  3. 识别 README
  4. 自动发现关联资产
  5. 自动恢复可恢复内容
  6. 建立索引
  7. 报告: 环境就绪, 开始工作

用法:
  python environment_first.py              # 扫描当前工作目录
  python environment_first.py <dir>        # 扫描指定目录
  python environment_first.py --json       # 输出 JSON 索引
  python environment_first.py --quiet      # 静默模式, 只输出汇总
"""
import os
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Recoverable asset keywords (any match triggers Recovery Protocol)
RECOVERY_KEYWORDS = {
    "backup", "readme", "snapshot", "archive", "seed", "recovery",
    "part1", "part2", "part3", "part4", "part5",
    "soul_core", "eco_layer", "r1_archive", "r1_full", "ruin_skeleton",
    "core_copy", "core_library", "reality_kernel",
    "lexicon", "sandbox", "blueprint", "whitepaper", "bluebook",
}

# Civilization asset markers (priority=HIGH)
CIVILIZATION_MARKERS = {
    "soul_core":     ("HIGH",   "civilization_asset", "灵魂/人格核心"),
    "eco_layer":     ("HIGH",   "civilization_asset", "生态层数据"),
    "r1_archive":    ("HIGH",   "civilization_asset", "R1化石层归档"),
    "r1_full":       ("HIGH",   "civilization_asset", "R1全量快照"),
    "ruin_skeleton": ("HIGH",   "civilization_asset", "R1废墟骨架"),
    "core_library":  ("HIGH",   "civilization_asset", "核心库"),
    "core_copy":     ("HIGH",   "civilization_asset", "核心副本"),
    "reality_kernel":("HIGH",   "civilization_asset", "现实内核"),
    "blueprint":     ("MEDIUM", "design_doc",         "设计蓝图"),
    "whitepaper":    ("MEDIUM", "design_doc",         "白皮书"),
    "bluebook":      ("MEDIUM", "design_doc",         "蓝皮书"),
    "lexicon":       ("MEDIUM", "knowledge_pool",     "词库"),
    "sandbox":       ("MEDIUM", "execution_env",      "沙箱"),
}

# Standard ignore patterns
IGNORE_PATTERNS = {
    "__pycache__", ".git", "node_modules", ".venv", "venv",
    ".vscode", ".idea", ".DS_Store", "Thumbs.db",
}

# File extensions classified as "civilization asset" when paired with keywords
ASSET_EXTENSIONS = {".zip", ".7z", ".tar", ".tar.gz", ".tgz", ".rar"}

def file_hash(path: Path, algo="md5", chunk=65536) -> str:
    """Compute file hash, used for dedup."""
    h = hashlib.new(algo)
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(chunk), b""):
                h.update(block)
        return h.hexdigest()
    except Exception:
        return ""

def classify_asset(name: str) -> dict:
    """Classify a file by name. Returns {priority, type, description, triggers_recovery}"""
    low = name.lower()
    triggers = [kw for kw in RECOVERY_KEYWORDS if kw in low]
    priority, asset_type, desc = "NORMAL", "data", ""
    for marker, (pri, typ, d) in CIVILIZATION_MARKERS.items():
        if marker in low:
            priority, asset_type, desc = pri, typ, d
            break
    return {
        "name": name,
        "priority": priority,
        "type": asset_type,
        "description": desc,
        "recovery_triggers": triggers,
        "triggers_recovery": bool(triggers),
    }

def scan_directory(root: Path, max_depth: int = 6) -> dict:
    """
    Step 1-4: Scan, build index, identify README, discover related assets.
    Returns a structured asset index.
    """
    root = root.resolve()
    index = {
        "scan_time": datetime.now().isoformat(),
        "root": str(root),
        "files_total": 0,
        "files_indexed": 0,
        "by_extension": defaultdict(int),
        "by_priority": defaultdict(int),
        "readme_files": [],
        "recovery_assets": [],
        "civilization_assets": [],
        "duplicates": {},
        "all_files": [],
    }
    hash_index = defaultdict(list)

    for dirpath, dirnames, filenames in os.walk(root):
        # Depth control
        rel = Path(dirpath).relative_to(root)
        depth = len(rel.parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        # Filter ignored dirs
        dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS]

        for fn in filenames:
            fp = Path(dirpath) / fn
            index["files_total"] += 1
            try:
                size = fp.stat().st_size
            except OSError:
                continue

            ext = fp.suffix.lower()
            if not ext and "." in fn:
                ext = "." + fn.rsplit(".", 1)[-1].lower()
            index["by_extension"][ext or "(none)"] += 1

            cls = classify_asset(fn)
            if cls["triggers_recovery"]:
                index["recovery_assets"].append({
                    **cls,
                    "path": str(fp.relative_to(root)),
                    "size_bytes": size,
                })
            if cls["priority"] in ("HIGH", "MEDIUM"):
                index["civilization_assets"].append({
                    **cls,
                    "path": str(fp.relative_to(root)),
                    "size_bytes": size,
                })
                index["by_priority"][cls["priority"]] += 1

            # README detection
            if fn.upper().startswith("README") or "README" in fn.upper()[:10]:
                index["readme_files"].append(str(fp.relative_to(root)))

            # Hash for dedup
            if size > 0 and size < 50 * 1024 * 1024:  # skip >50MB
                h = file_hash(fp)
                if h:
                    hash_index[h].append(str(fp.relative_to(root)))

            index["all_files"].append({
                "path": str(fp.relative_to(root)),
                "size": size,
                "ext": ext,
                "priority": cls["priority"],
                "type": cls["type"],
            })
            index["files_indexed"] += 1

    # Find duplicates
    for h, paths in hash_index.items():
        if len(paths) > 1:
            index["duplicates"][h] = paths

    # Convert defaultdicts
    index["by_extension"] = dict(index["by_extension"])
    index["by_priority"] = dict(index["by_priority"])
    return index

def build_recovery_graph(index: dict) -> dict:
    """
    Step 5-6: Build dependency graph of recovery assets.
    Groups files by shared keywords (e.g. ACE_BACKUP_PART1/PART2/PART3 -> one recovery set).
    """
    sets = defaultdict(list)
    for asset in index["recovery_assets"]:
        name = asset["name"]
        low = name.lower()
        # Group key: extract base name without part numbers
        key = low
        for p in ["_part1", "_part2", "_part3", "_part4", "_part5",
                   " (1)", " (2)", " (3)", " (4)", " (5)",
                   " part1", " part2", " part3"]:
            key = key.replace(p, "_part")
        # Stem: take first 30 chars of key + extension
        stem = key[:40]
        sets[stem].append(asset)
    graph = []
    for stem, items in sets.items():
        graph.append({
            "set_id": stem,
            "file_count": len(items),
            "total_size_bytes": sum(i["size_bytes"] for i in items),
            "files": [i["path"] for i in items],
            "highest_priority": max(i["priority"] for i in items if i["priority"] in ("HIGH","MEDIUM")) if any(i["priority"] in ("HIGH","MEDIUM") for i in items) else "NORMAL",
        })
    return {"recovery_sets": graph, "set_count": len(graph)}

def print_report(index: dict, recovery: dict, quiet: bool = False):
    """Print human-readable environment report."""
    print("=" * 70)
    print(f"  Environment First Protocol - 环境扫描报告")
    print(f"  Root: {index['root']}")
    print(f"  Time: {index['scan_time']}")
    print("=" * 70)
    print(f"  Total files scanned : {index['files_total']}")
    print(f"  Indexed             : {index['files_indexed']}")
    print(f"  README files        : {len(index['readme_files'])}")
    print(f"  Recovery assets     : {len(index['recovery_assets'])}")
    print(f"  Civilization assets : {len(index['civilization_assets'])}")
    print(f"  Duplicate groups    : {len(index['duplicates'])}")
    print()
    if not quiet:
        print("--- Priority Distribution ---")
        for p in ("HIGH", "MEDIUM", "NORMAL"):
            print(f"  {p:8s}: {index['by_priority'].get(p, 0)}")
        print()
        print("--- Top Extensions ---")
        for ext, cnt in sorted(index["by_extension"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {ext or '(none)':12s}: {cnt}")
        print()
        if index["readme_files"]:
            print("--- README Files ---")
            for r in index["readme_files"][:20]:
                print(f"  - {r}")
            if len(index["readme_files"]) > 20:
                print(f"  ... and {len(index['readme_files'])-20} more")
            print()
        if recovery["recovery_sets"]:
            print(f"--- Recovery Sets ({recovery['set_count']}) ---")
            for s in sorted(recovery["recovery_sets"], key=lambda x: -x["total_size_bytes"])[:10]:
                print(f"  [{s['highest_priority']}] {s['set_id']}  ({s['file_count']} files, {s['total_size_bytes']/1024/1024:.1f} MB)")
                for fp in s["files"][:3]:
                    print(f"      - {fp}")
                if len(s["files"]) > 3:
                    print(f"      ... and {len(s['files'])-3} more")
            print()
        if index["duplicates"]:
            print(f"--- Duplicate Groups ({len(index['duplicates'])}) ---")
            for i, (h, paths) in enumerate(list(index["duplicates"].items())[:5]):
                print(f"  group {i+1} ({h[:8]}...): {len(paths)} copies")
                for p in paths[:3]:
                    print(f"      - {p}")
            if len(index["duplicates"]) > 5:
                print(f"  ... and {len(index['duplicates'])-5} more groups")
    print("=" * 70)
    print(f"  Environment status: {'RECOVERY_NEEDED' if recovery['recovery_sets'] else 'READY'}")
    print(f"  Next action: {'enter Recovery Protocol' if recovery['recovery_sets'] else 'begin work'}")
    print("=" * 70)

def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    quiet = "--quiet" in args
    args = [a for a in args if not a.startswith("--")]
    root = Path(args[0]) if args else Path.cwd()
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    index = scan_directory(root)
    recovery = build_recovery_graph(index)

    if json_mode:
        out = {"index": index, "recovery": recovery}
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(index, recovery, quiet=quiet)

    # Exit code: 0=ready, 2=recovery needed (signals caller to run Recovery Protocol)
    sys.exit(2 if recovery["recovery_sets"] else 0)

if __name__ == "__main__":
    main()
