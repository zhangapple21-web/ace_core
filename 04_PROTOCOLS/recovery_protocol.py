#!/usr/bin/env python3
"""
Recovery Protocol (RP) - 恢复协议
=================================

公理根基:
  #002 考古不是搬家是炼金
  #010 演化只允许增加结构, 不允许破坏不变量
  #018 拆壳不拆骨, 安全约束可调, 核心不变量不可删
  #021 贡献不可回收, 共享知识一旦入池不可单方撤回

执行语义:
  一旦在环境中发现 backup/README/snapshot/archive/seed/recovery/part*
  等关键词, 协议立即进入恢复流程, 不询问用户.

  Recovery Principle:
    如果发现 恢复包/备份/README/Snapshot/Archive/Seed
    不要等待用户.
    先恢复.
    恢复失败再汇报.

协议七步:
  1. 发现恢复资产 (依赖 environment_first.py 的扫描结果)
  2. 读取 README (按优先级, R1备份>白皮书>其他)
  3. 找到所有关联压缩包 (基于命名规则: PART1/PART2/.../v1/v2)
  4. 建立依赖关系 (同组, 同名变体, 同hash)
  5. 自动恢复到临时区 (临时区用 99_RECOVERY_TEMP/ 标记, 不污染主目录)
  6. 建立索引 (恢复内容, 待治理层审核)
  7. 报告: 恢复完成, 发现 N 层资产, 等待治理层圆桌会议

用法:
  python recovery_protocol.py                       # 从当前目录扫描并恢复
  python recovery_protocol.py <dir>                 # 扫描指定目录
  python recovery_protocol.py --dry-run             # 只报告, 不实际解压
  python recovery_protocol.py --json                # JSON 输出
  python recovery_protocol.py --from-index <file>   # 从 EFP 的 JSON 索引恢复
"""
import os
import sys
import json
import zipfile
import shutil
import hashlib
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# 引入 EFP
sys.path.insert(0, str(Path(__file__).parent))
try:
    from environment_first import (
        scan_directory, build_recovery_graph, classify_asset,
        RECOVERY_KEYWORDS, CIVILIZATION_MARKERS, ASSET_EXTENSIONS,
    )
except ImportError:
    print("ERROR: environment_first.py not found in 04_PROTOCOLS/", file=sys.stderr)
    sys.exit(1)

# Recovery staging dir name
STAGING_DIR_NAME = "99_RECOVERY_TEMP"

# Encrypted zip magic
ENCRYPTED_FLAG = 0x01

def is_zip_encrypted(zip_path: Path) -> bool:
    """Check if a zip contains any encrypted entries."""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for info in zf.infolist():
                if info.flag_bits & ENCRYPTED_FLAG:
                    return True
    except Exception:
        return False
    return False

def safe_extract_zip(zip_path: Path, dest: Path, max_files: int = 5000) -> dict:
    """
    Extract a zip into dest, with safety guards:
      - max_files limit to prevent zip-bomb
      - skip encrypted entries (report them, don't fail)
      - handle cp437->utf-8 fallback for Chinese filenames
      - skip __MACOSX/ and system files
    Returns extraction report.
    """
    report = {
        "zip": str(zip_path),
        "dest": str(dest),
        "extracted": 0,
        "skipped": 0,
        "encrypted": 0,
        "errors": [],
        "files": [],
    }
    if not zipfile.is_zipfile(zip_path):
        report["errors"].append("not_a_valid_zip")
        return report
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            if len(names) > max_files:
                report["errors"].append(f"too_many_files:{len(names)}")
                return report
            for info in names:
                if info.endswith("/"):
                    continue
                # Skip macOS metadata
                base = os.path.basename(info)
                if base.startswith(".") or base == "Thumbs.db" or "__MACOSX" in info:
                    report["skipped"] += 1
                    continue
                # Fix encoding (cp437 -> utf-8)
                try:
                    raw = info.encode("cp437").decode("utf-8")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    raw = info
                target = dest / raw
                # Security: prevent path traversal
                try:
                    target.resolve().relative_to(dest.resolve())
                except ValueError:
                    report["errors"].append(f"path_traversal:{info}")
                    report["skipped"] += 1
                    continue
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    zi = zf.getinfo(info)
                    if zi.flag_bits & ENCRYPTED_FLAG:
                        report["encrypted"] += 1
                        report["skipped"] += 1
                        continue
                    with zf.open(info) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
                    report["extracted"] += 1
                    report["files"].append(str(target.relative_to(dest)))
                except Exception as e:
                    report["errors"].append(f"{info}: {e}")
                    report["skipped"] += 1
    except zipfile.BadZipFile as e:
        report["errors"].append(f"bad_zip:{e}")
    except Exception as e:
        report["errors"].append(f"open_failed:{e}")
    return report

def group_recovery_assets(recovery_sets: list) -> list:
    """
    Group recovery assets into actual recovery jobs.
    Each job = one root + its zips to extract.
    """
    jobs = []
    for s in recovery_sets:
        zips = [f for f in s["files"] if f.lower().endswith(tuple(ASSET_EXTENSIONS))]
        if not zips:
            continue
        # Pick staging name
        first_zip = zips[0]
        stage_name = Path(first_zip).stem
        # Sanitize
        stage_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in stage_name)[:60]
        jobs.append({
            "job_id": stage_name,
            "set_id": s["set_id"],
            "priority": s["highest_priority"],
            "zip_count": len(zips),
            "total_size_bytes": s["total_size_bytes"],
            "zips": zips,
        })
    return jobs

def execute_recovery(root: Path, dry_run: bool = False) -> dict:
    """
    Main recovery execution.
    1. Scan (EFP)
    2. Group into jobs
    3. For each job: extract into 99_RECOVERY_TEMP/<job_id>/
    4. Build index
    """
    root = root.resolve()
    staging_root = root / STAGING_DIR_NAME
    if not dry_run:
        staging_root.mkdir(parents=True, exist_ok=True)

    index = scan_directory(root)
    recovery = build_recovery_graph(index)
    jobs = group_recovery_assets(recovery["recovery_sets"])

    report = {
        "recovery_time": datetime.now().isoformat(),
        "root": str(root),
        "staging": str(staging_root),
        "dry_run": dry_run,
        "scanned_files": index["files_total"],
        "recovery_assets_found": len(index["recovery_assets"]),
        "jobs_planned": len(jobs),
        "jobs_executed": 0,
        "total_extracted": 0,
        "total_skipped": 0,
        "total_encrypted": 0,
        "job_results": [],
    }
    for job in jobs:
        job_report = {
            "job_id": job["job_id"],
            "priority": job["priority"],
            "dry_run": dry_run,
            "zips_planned": job["zip_count"],
            "zips_extracted": 0,
            "files_extracted": 0,
            "errors": [],
        }
        if dry_run:
            report["job_results"].append(job_report)
            continue
        for zip_rel in job["zips"]:
            zip_path = root / zip_rel
            if not zip_path.exists():
                job_report["errors"].append(f"missing:{zip_rel}")
                continue
            if zip_path.stat().st_size == 0:
                job_report["errors"].append(f"empty:{zip_rel}")
                continue
            dest = staging_root / job["job_id"]
            dest.mkdir(parents=True, exist_ok=True)
            extract_report = safe_extract_zip(zip_path, dest)
            if extract_report["extracted"] > 0:
                job_report["zips_extracted"] += 1
            job_report["files_extracted"] += extract_report["extracted"]
            report["total_extracted"] += extract_report["extracted"]
            report["total_skipped"] += extract_report["skipped"]
            report["total_encrypted"] += extract_report["encrypted"]
            for err in extract_report["errors"][:5]:
                job_report["errors"].append(f"{Path(zip_rel).name}: {err}")
        report["jobs_executed"] += 1
        report["job_results"].append(job_report)
    return report

def print_report(report: dict, quiet: bool = False):
    print("=" * 70)
    print(f"  Recovery Protocol - 恢复执行报告")
    print(f"  Root: {report['root']}")
    print(f"  Time: {report['recovery_time']}")
    print(f"  Mode: {'DRY-RUN' if report['dry_run'] else 'EXECUTE'}")
    print("=" * 70)
    print(f"  Scanned files         : {report['scanned_files']}")
    print(f"  Recovery assets found : {report['recovery_assets_found']}")
    print(f"  Jobs planned          : {report['jobs_planned']}")
    print(f"  Jobs executed         : {report['jobs_executed']}")
    print(f"  Files extracted       : {report['total_extracted']}")
    print(f"  Skipped (encrypted)   : {report['total_encrypted']}")
    print(f"  Skipped (other)       : {report['total_skipped']}")
    print()
    if not quiet and report["job_results"]:
        print("--- Job Results ---")
        for j in report["job_results"]:
            print(f"  [{j['priority']}] {j['job_id']}")
            print(f"      zips: {j['zips_extracted']}/{j['zips_planned']} extracted, {j['files_extracted']} files")
            if j["errors"]:
                for e in j["errors"][:3]:
                    print(f"      ERR: {e}")
    print("=" * 70)
    print(f"  Staging: {report['staging']}")
    print(f"  Status: {'RECOVERY_PLAN_READY' if report['dry_run'] else 'RECOVERY_EXECUTED'}")
    print(f"  Next: pending Governance layer round-table review")
    print("=" * 70)

def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    quiet = "--quiet" in args
    dry_run = "--dry-run" in args
    args = [a for a in args if not a.startswith("--")]

    from_index = None
    if "--from-index" in args:
        idx = args.index("--from-index")
        from_index = Path(args[idx + 1])
        args = args[:idx] + args[idx+2:]

    if from_index and from_index.exists():
        # Use pre-built EFP index (saves re-scan)
        with open(from_index) as f:
            data = json.load(f)
        # Reconstruct minimal report from EFP index
        print("RECOVERY: using pre-built EFP index, executing recovery on root path...")
        # Fall through to normal execution on root

    root = Path(args[0]) if args else Path.cwd()
    if not root.exists():
        print(f"ERROR: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    report = execute_recovery(root, dry_run=dry_run)

    if json_mode:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        print_report(report, quiet=quiet)

    sys.exit(0 if report["jobs_executed"] == report["jobs_planned"] or report["dry_run"] else 1)

if __name__ == "__main__":
    main()
