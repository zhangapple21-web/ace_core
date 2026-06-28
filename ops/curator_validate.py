#!/usr/bin/env python3
"""馆长每日流程验证脚本 — 对今日产物执行一次完整馆长流程"""
import sys
from pathlib import Path

# 添加到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.repository_curator import RepositoryCurator
from core.similarity_engine import SimilarityEngine
from core.value_scorer import ValueScorer
from core.sync_manager import SyncManager


def main():
    ace_runtime = Path(__file__).parent.parent.resolve()
    mine_seed = Path.home() / ".trae" / "work" / "6a3be8d2084d33999ccdf8c7" / "repos" / "mine-seed"

    print("=" * 60)
    print("Repository Curator — 每日流程验证")
    print("=" * 60)
    print(f"ace_runtime: {ace_runtime}")
    print(f"mine_seed:   {mine_seed}")
    print()

    # 初始化组件
    data_dir = ace_runtime / "06_RUNTIME" / "ace" / "data" / "curator"
    data_dir.mkdir(parents=True, exist_ok=True)

    sim_engine = SimilarityEngine(str(data_dir))
    val_scorer = ValueScorer(data_dir=str(data_dir))
    sync_mgr = SyncManager(data_dir=str(data_dir))

    curator = RepositoryCurator(
        ace_runtime_dir=str(ace_runtime),
        mine_seed_dir=str(mine_seed) if mine_seed.exists() else "",
        ace_core_dir=str(ace_runtime),
        similarity_engine=sim_engine,
        value_scorer=val_scorer,
        sync_manager=sync_mgr,
        data_dir=str(data_dir),
    )

    # 执行馆长流程
    print("馆长正在审查产物...")
    print()

    result = curator.wakeup(triggered_by="manual_validation")

    # 打印结果
    print()
    print("=" * 60)
    print("馆长报告")
    print("=" * 60)
    print(f"触发方式: {result.get('triggered_by')}")
    print(f"执行时间: {result.get('started_at')} → {result.get('finished_at')}")
    print(f"耗时: {result.get('duration_seconds', 0):.1f}s")
    print()
    print(f"扫描产物: {result.get('artifacts_scanned')} 个")

    summary = result.get("summary", "无")
    print(f"决策摘要: {summary}")
    print()

    decisions = result.get("decisions", [])
    if decisions:
        print("详细决策:")
        for d in decisions:
            print(f"  [{d.get('action', '?').upper():8}] {d.get('title', '?')[:50]}")
            print(f"    目标: {d.get('target_repo', '?')}/{d.get('target_path', '?')}")
            print(f"    理由: {d.get('reason', '')[:60]}")
            print()
    else:
        print("无产物需要处理（所有产物已同步或已丢弃）")

    duplicates = result.get("duplicates_found", [])
    if duplicates:
        print(f"⚠️ 发现重复产物: {len(duplicates)} 个（馆长已标记为 update）")

    splits = result.get("split_candidates", [])
    if splits:
        print(f"⚠️ 需拆分产物: {len(splits)} 个（馆长已标记为 split）")

    # 权限矩阵
    print()
    print("=" * 60)
    print("馆长权限矩阵")
    print("=" * 60)
    from core.repository_curator import PERMISSION_MATRIX
    for agent, perms in PERMISSION_MATRIX.items():
        print(f"  {agent}:")
        for action, allowed in perms.items():
            flag = "✅" if allowed else "❌"
            print(f"    {flag} {action}")


if __name__ == "__main__":
    main()
