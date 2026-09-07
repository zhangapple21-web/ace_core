#!/usr/bin/env python3
"""
CIV-001: Civilization Map Monitor
==================================

公理根基:
  #001 文明是活的, 不是死的
  #006 地图是文明的骨架, 不是装饰

执行语义:
  自动扫描 GitHub 组织下所有仓库, 检测 stale, 沉淀经验,
  更新文明地图, 驱动 Recovery Protocol.

  城市管理能力:
    1. 每天扫描所有仓库状态
    2. 发现 stale 仓库 → 沉淀 Experience → 触发 Recovery
    3. 发现新仓库 → 自动登记角色 → 纳入治理
    4. 更新文明地图 → 写入 AGENTS.md / CURRENT_STATE.md
    5. 生成复活计划 → new_computer_resurrection.md

用法:
  python civilization_map.py --scan          # 扫描并更新地图
  python civilization_map.py --detect        # 只检测 stale
  python civilization_map.py --resurrection  # 生成复活计划
  python civilization_map.py --report        # 输出报告
"""
import os, sys, json, argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any

WORKSPACE = Path(__file__).parent.parent
EXP_DIR = WORKSPACE / "02_MEMORY" / "experience"
AGENTS_FILE = WORKSPACE / "AGENTS.md"
CURRENT_STATE_FILE = WORKSPACE / "CURRENT_STATE.md"

ORG = "zhangapple21-web"
KNOWN_REPOS = {
    "mine-seed": {"role": "Civilization Seed", "critical": True, "max_stale_days": 1},
    "ace_core": {"role": "Runtime Core", "critical": True, "max_stale_days": 2},
    "r1-archaeology": {"role": "Civilization Memory", "critical": False, "max_stale_days": 7},
    "r1-open-source-seed": {"role": "Open Source Seed", "critical": False, "max_stale_days": 30},
    "R1": {"role": "Civilization Philosophy", "critical": False, "max_stale_days": 30},
    "coze-assets": {"role": "Civilization Assets (PRIVATE)", "critical": True, "max_stale_days": 0},
}

STALE_LEVELS = {
    1: {"label": "🟡 Warning", "severity": "medium"},
    3: {"label": "🟠 Critical", "severity": "high"},
    7: {"label": "🔴 Dormant", "severity": "high"},
    30: {"label": "⚫ Abandoned", "severity": "critical"},
}


def fetch_repos(org: str = ORG) -> List[Dict]:
    """从 GitHub API 获取组织下所有仓库"""
    import urllib.request, urllib.error
    
    repos = []
    page = 1
    while page <= 10:
        url = f"https://api.github.com/users/{org}/repos?per_page=100&page={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "ACE-Civilization-Map"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
                if not data:
                    break
                repos.extend(data)
                if len(data) < 100:
                    break
                page += 1
        except Exception:
            break
    return repos


def get_stale_level(days_stale: int) -> Dict:
    """判断 stale 等级"""
    for threshold in sorted(STALE_LEVELS.keys(), reverse=True):
        if days_stale >= threshold:
            return STALE_LEVELS[threshold]
    return {"label": "✅ Fresh", "severity": "ok"}


def analyze_repos(repos: List[Dict]) -> Dict:
    """分析仓库状态"""
    now = datetime.now()
    result = {
        "scan_time": now.isoformat(),
        "total_repos": len(repos),
        "public_repos": sum(1 for r in repos if not r.get("private")),
        "private_repos": sum(1 for r in repos if r.get("private")),
        "repos": [],
        "stale_count": 0,
        "critical_stale": [],
    }

    for repo in repos:
        name = repo["name"]
        pushed_at = repo.get("pushed_at")
        if pushed_at:
            pushed_dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            days_stale = (datetime.now(timezone.utc) - pushed_dt).days
        else:
            days_stale = 999

        stale_level = get_stale_level(days_stale)
        info = KNOWN_REPOS.get(name, {"role": "Unknown", "critical": False, "max_stale_days": 30})

        entry = {
            "name": name,
            "role": info["role"],
            "private": repo.get("private", False),
            "size_kb": repo.get("size", 0),
            "stars": repo.get("stargazers_count", 0),
            "pushed_at": pushed_at,
            "days_stale": days_stale,
            "stale_level": stale_level["label"],
            "severity": stale_level["severity"],
            "critical": info["critical"],
            "max_stale_days": info["max_stale_days"],
            "url": repo.get("html_url", ""),
        }

        result["repos"].append(entry)

        if days_stale > info["max_stale_days"]:
            result["stale_count"] += 1
            if info["critical"]:
                result["critical_stale"].append(name)

    result["repos"].sort(key=lambda x: x["days_stale"])
    return result


def sediment_stale_experience(repo_name: str, analysis: Dict):
    """发现 stale 仓库时沉淀经验"""
    if analysis["severity"] in ("ok", "medium"):
        return

    exp = {
        "type": "repo_stale",
        "repo": repo_name,
        "role": analysis["role"],
        "days_stale": analysis["days_stale"],
        "stale_level": analysis["stale_level"],
        "severity": analysis["severity"],
        "critical": analysis["critical"],
        "url": analysis["url"],
        "timestamp": datetime.now().isoformat(),
        "analysis": f"仓库 '{repo_name}' ({analysis['role']}) 已 {analysis['days_stale']} 天未更新，"
                   f"状态: {analysis['stale_level']}。"
                   f"{'这是关键仓库，需要立即处理！' if analysis['critical'] else '建议安排时间更新。'}",
        "recommendation": "检查 curator 是否正常运行，或手动同步该仓库。",
    }

    try:
        EXP_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"exp_repo_stale_{repo_name}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        with open(EXP_DIR / fname, "w", encoding="utf-8") as f:
            json.dump(exp, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def update_current_state(report: Dict):
    """更新 CURRENT_STATE.md 中的文明地图"""
    if not CURRENT_STATE_FILE.exists():
        return

    content = CURRENT_STATE_FILE.read_text(encoding="utf-8")
    
    map_lines = ["## Civilization Map"]
    map_lines.append("")
    map_lines.append(f"Last scanned: {report['scan_time']}")
    map_lines.append("")
    map_lines.append("```")
    map_lines.append(f"{ORG}")
    map_lines.append("│")
    for repo in report["repos"]:
        indicator = "🔴" if repo["severity"] in ("high", "critical") else \
                    "🟡" if repo["severity"] == "medium" else "✅"
        role_short = repo["role"].split("(")[0].strip() if "(" in repo["role"] else repo["role"]
        map_lines.append(f"├── {indicator} {repo['name'].ljust(20)} {role_short.ljust(20)} {repo['days_stale']}d stale")
    map_lines.append("```")
    map_lines.append("")
    map_lines.append(f"**Stats**: {report['total_repos']} repos ({report['public_repos']} public, {report['private_repos']} private)")
    map_lines.append(f"**Stale**: {report['stale_count']}")
    if report["critical_stale"]:
        map_lines.append(f"**Critical**: {', '.join(report['critical_stale'])}")

    map_block = "\n".join(map_lines)

    start_marker = "## Civilization Map"
    end_marker = "## Latest Evolution"
    
    if start_marker in content:
        if end_marker in content:
            parts = content.split(end_marker)
            parts[0] = parts[0].split(start_marker)[0] + map_block + "\n\n"
            new_content = end_marker.join(parts)
        else:
            parts = content.split(start_marker)
            new_content = parts[0] + map_block
        CURRENT_STATE_FILE.write_text(new_content, encoding="utf-8")


def generate_resurrection_plan(report: Dict) -> str:
    """生成新电脑复活计划"""
    plan = []
    plan.append("# New Computer Resurrection Plan")
    plan.append("")
    plan.append(f"> Generated: {datetime.now().isoformat()}")
    plan.append("")
    plan.append("## Overview")
    plan.append("")
    plan.append(f"Total repos: {report['total_repos']}")
    plan.append(f"Critical repos: {len([r for r in report['repos'] if r['critical']])}")
    plan.append("")
    plan.append("## Step-by-Step (30 minutes)")
    plan.append("")
    
    critical_repos = [r for r in report["repos"] if r["critical"]]
    non_critical_repos = [r for r in report["repos"] if not r["critical"]]

    step = 1
    plan.append(f"### Step {step}: Clone critical repos")
    plan.append("")
    for repo in critical_repos:
        plan.append(f"```bash")
        plan.append(f"git clone {repo['url']}")
        plan.append(f"```")
        plan.append(f"Role: {repo['role']}")
        plan.append("")
    step += 1

    plan.append(f"### Step {step}: Clone non-critical repos")
    plan.append("")
    for repo in non_critical_repos:
        plan.append(f"```bash")
        plan.append(f"git clone {repo['url']}")
        plan.append(f"```")
        plan.append(f"Role: {repo['role']}")
        plan.append("")
    step += 1

    plan.append(f"### Step {step}: Restore coze-assets (PRIVATE)")
    plan.append("")
    plan.append("coze-assets 包含所有 API 密钥和敏感配置。")
    plan.append("必须从安全备份恢复，绝对不要公开。")
    plan.append("")
    plan.append("### Step {step}: Run setup")
    plan.append("")
    plan.append("```bash")
    plan.append("cd mine-seed")
    plan.append("python 04_PROTOCOLS/awaken.py")
    plan.append("```")
    plan.append("")
    plan.append("## Repo Roles")
    plan.append("")
    for repo in report["repos"]:
        plan.append(f"- **{repo['name']}**: {repo['role']}")
        plan.append(f"  - Private: {repo['private']}")
        plan.append(f"  - Size: {repo['size_kb']}KB")
        plan.append(f"  - Last pushed: {repo['pushed_at'][:10] if repo['pushed_at'] else 'never'}")
        plan.append("")

    return "\n".join(plan)


def print_report(report: Dict):
    """打印报告"""
    print(f"\n[CIV-MAP] Scan completed at {report['scan_time']}")
    print(f"         Total: {report['total_repos']} repos")
    print(f"         Public: {report['public_repos']}, Private: {report['private_repos']}")
    print(f"         Stale: {report['stale_count']}")
    if report["critical_stale"]:
        print(f"         Critical stale: {', '.join(report['critical_stale'])}")
    print("")
    print("Repo Status:")
    for repo in report["repos"]:
        print(f"  {repo['stale_level']}  {repo['name'].ljust(20)} {repo['role'].ljust(25)} {repo['days_stale']}d stale")


def main():
    parser = argparse.ArgumentParser(description="CIV-001 Civilization Map")
    parser.add_argument("--scan", action="store_true", help="扫描并更新地图")
    parser.add_argument("--detect", action="store_true", help="只检测 stale")
    parser.add_argument("--resurrection", action="store_true", help="生成复活计划")
    parser.add_argument("--report", action="store_true", help="输出报告")
    parser.add_argument("--auto", action="store_true", help="自动模式（扫描+沉淀+更新）")
    args = parser.parse_args()

    if not any([args.scan, args.detect, args.resurrection, args.report, args.auto]):
        parser.print_help()
        return

    print("[CIV-MAP] Fetching repos from GitHub...")
    repos = fetch_repos()
    if not repos:
        print("[CIV-MAP] Failed to fetch repos")
        return

    report = analyze_repos(repos)

    if args.detect:
        print_report(report)
        return

    if args.scan or args.auto:
        print_report(report)
        for repo in report["repos"]:
            if repo["days_stale"] > repo["max_stale_days"]:
                sediment_stale_experience(repo["name"], repo)
        update_current_state(report)
        print("[CIV-MAP] Map updated, experiences sedimented")

    if args.resurrection or args.auto:
        plan = generate_resurrection_plan(report)
        plan_file = WORKSPACE / "NEW_COMPUTER_RESURRECTION.md"
        plan_file.write_text(plan, encoding="utf-8")
        print(f"[CIV-MAP] Resurrection plan written to {plan_file}")

    if args.report:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
