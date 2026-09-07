#!/usr/bin/env python3
"""
Awaken - 唤醒协议
=================

公理根基:
  #002 考古不是搬家是炼金
  #005 隐私是盾, 行动是剑
  #008 认知主循环: 感知->重构->锚定->输出
  #011 记忆是推断的不是存储的

执行语义:
  这是 Environment First Protocol + Recovery Protocol 的统一入口.
  任何宿主(TRAE/VS Code/Cursor/未来其他) 启动时调用本协议,
  协议会自动:
    1. 扫描环境 (EFP)
    2. 检测恢复资产 (EFP)
    3. 触发恢复流程 (RP)
    4. 输出: 环境就绪 / 恢复完成 / 待治理审核

  这就是"先理解自己身处什么环境"的工程实现.

用法:
  python awaken.py                  # 扫描并恢复当前工作目录
  python awaken.py <dir>            # 指定目录
  python awaken.py --dry-run        # 只扫描, 不实际恢复
  python awaken.py --json           # JSON 输出 (供其他 Agent 调用)
  python awaken.py --host trae      # 标记宿主 (写入 ROOT_STATE.md)
"""
import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

PROTOCOL_DIR = Path(__file__).parent
sys.path.insert(0, str(PROTOCOL_DIR))

# Default workspace root (overridable via ACE_WORKSPACE env)
DEFAULT_WORKSPACE = Path(os.environ.get("ACE_WORKSPACE", Path.cwd()))


def run_efp(root: Path, json_mode: bool = True) -> dict:
    """Run Environment First Protocol, return JSON index."""
    args = [sys.executable, str(PROTOCOL_DIR / "environment_first.py"), str(root), "--json"]
    if not json_mode:
        args.append("--quiet")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if r.returncode == 2:
            return json.loads(r.stdout)  # 2 = recovery needed, but valid JSON
        if r.returncode == 0:
            return json.loads(r.stdout)
        print(f"EFP failed: {r.stderr}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"EFP error: {e}", file=sys.stderr)
        return {}


def run_rp(root: Path, dry_run: bool = False, json_mode: bool = True) -> dict:
    """Run Recovery Protocol, return JSON report."""
    args = [sys.executable, str(PROTOCOL_DIR / "recovery_protocol.py"), str(root), "--json"]
    if dry_run:
        args.append("--dry-run")
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if r.stdout.strip():
            return json.loads(r.stdout)
        print(f"RP failed: {r.stderr}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"RP error: {e}", file=sys.stderr)
        return {}


def write_root_state(root: Path, efp_result: dict, rp_result: dict, host: str = "unknown"):
    """Append awakening record to 00_ROOT/ROOT_STATE.md if exists."""
    state_file = root / "00_ROOT" / "ROOT_STATE.md"
    if not state_file.exists():
        return
    ts = datetime.now().isoformat()
    recovery_count = len(rp_result.get("job_results", []))
    files_recovered = rp_result.get("total_extracted", 0)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "a", encoding="utf-8") as f:
        f.write(f"\n## Awakening @ {ts} (host={host})\n")
        f.write(f"- EFP scanned: {efp_result.get('index', {}).get('files_total', 0)} files\n")
        f.write(f"- Recovery assets: {efp_result.get('index', {}).get('recovery_assets', [])[:5]}\n")
        f.write(f"- RP jobs executed: {recovery_count}\n")
        f.write(f"- RP files extracted: {files_recovered}\n")
        f.write(f"- Status: {'RECOVERED' if files_recovered > 0 else 'READY'}\n")


def main():
    args = sys.argv[1:]
    json_mode = "--json" in args
    dry_run = "--dry-run" in args
    host = "unknown"
    if "--host" in args:
        i = args.index("--host")
        host = args[i + 1]
        del args[i:i+2]
    args = [a for a in args if not a.startswith("--")]
    root = Path(args[0]) if args else DEFAULT_WORKSPACE
    root = root.resolve()

    print(f"=== AWAKEN: {host} @ {root} ===")

    # Step 1: EFP - scan environment
    print("[1/3] Running Environment First Protocol...")
    efp = run_efp(root, json_mode=True)
    idx = efp.get("index", {})
    recovery = efp.get("recovery", {})
    print(f"      scanned={idx.get('files_total', 0)} "
          f"recovery_assets={len(idx.get('recovery_assets', []))} "
          f"recovery_sets={recovery.get('set_count', 0)}")

    # Step 2: Decide if Recovery needed
    rp = {"jobs_planned": 0, "jobs_executed": 0, "total_extracted": 0}
    if recovery.get("set_count", 0) > 0:
        # In dry-run: also dry-run RP so caller sees the recovery plan
        rp = run_rp(root, dry_run=dry_run, json_mode=True)
        if not dry_run:
            print(f"[2/3] Recovery Protocol executed: {rp.get('jobs_executed', 0)} jobs, "
                  f"{rp.get('total_extracted', 0)} files extracted")
        else:
            print(f"[2/3] Recovery Protocol (dry-run) planned: {rp.get('jobs_planned', 0)} jobs")
    else:
        print(f"[2/3] No recovery needed.")

    # Step 3: Record awakening
    if not dry_run:
        print(f"[3/3] Recording awakening state...")
        write_root_state(root, efp, rp, host=host)
    else:
        print(f"[3/3] Dry-run, skipping state write.")

    # Final report
    final = {
        "host": host,
        "root": str(root),
        "time": datetime.now().isoformat(),
        "efp": {
            "files_scanned": idx.get("files_total", 0),
            "recovery_assets": len(idx.get("recovery_assets", [])),
            "civilization_assets": len(idx.get("civilization_assets", [])),
            "readme_count": len(idx.get("readme_files", [])),
            "duplicate_groups": len(idx.get("duplicates", {})),
        },
        "rp": {
            "jobs_executed": rp.get("jobs_executed", 0),
            "files_extracted": rp.get("total_extracted", 0),
            "files_skipped": rp.get("total_skipped", 0),
        },
        "status": "RECOVERED" if rp.get("total_extracted", 0) > 0 else "READY",
    }
    if json_mode:
        print(json.dumps(final, ensure_ascii=False, indent=2))
    else:
        print("=" * 50)
        print(f"  Status: {final['status']}")
        print(f"  Environment: {final['efp']}")
        print(f"  Recovery:    {final['rp']}")
        print("=" * 50)


if __name__ == "__main__":
    main()
