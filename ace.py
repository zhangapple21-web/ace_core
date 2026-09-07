#!/usr/bin/env python3
"""
ACE Runtime 主入口

用法：
  python ace.py run          # 持续运行（轮询模式）
  python ace.py once         # 处理一轮所有待处理任务
  python ace.py status       # 查看系统状态
  python ace.py submit "标题" "内容"  # 手动提交一个观察
  python ace.py protocol <任务ID>        # 查看任务开工协议回执（只读）
  python ace.py start <任务ID> <owner>    # 通过唯一 ACE 开工入口领取任务
  python ace.py test         # 运行端到端测试
  python ace.py daemon       # 运行一次自动考古主循环
"""

import json
import sys
from pathlib import Path


def load_config(base_dir: Path) -> dict:
    config_path = base_dir / "ace_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main(base_dir=None):
    base_dir = Path(base_dir or Path(__file__).parent).resolve()
    config = load_config(base_dir)

    if len(sys.argv) < 2:
        print("ACE Runtime v0.1")
        print()
        print("用法:")
        print("  python ace.py run          持续运行")
        print("  python ace.py once         处理一轮")
        print("  python ace.py status       查看状态")
        print("  python ace.py submit <标题> <内容>  提交观察")
        print("  python ace.py protocol <任务ID>       查看开工协议回执（只读）")
        print("  python ace.py start <任务ID> <owner>  通过唯一 ACE 开工入口领取任务")
        print("  python ace.py test         端到端测试")
        print()
        print("  python ace.py lexicon list                    列出词库概念")
        print("  python ace.py lexicon search <关键词>          搜索词库")
        print("  python ace.py lexicon classify <文本>          用词库分类文本")
        print()
        print("  python ace.py mem search <关键词>              搜索记忆索引")
        print("  python ace.py mem concept <概念名>              按概念查记忆")
        print("  python ace.py mem stats                       记忆索引统计")
        print()
        print("  python ace.py scan <路径>                      扫描磁盘路径")
        print("  python ace.py scan-fragments <路径>            查找碎片文件")
        print("  python ace.py assistant <问题>                 最小干扰助手")
        print()
        print("  python ace.py daemon                           运行一次自动考古主循环")
        print("  python ace.py daemon --dry-run                 只看决策，不执行")
        print("  python ace.py daemon --force                   强制运行，无新发现也产出")
        print("  python ace.py daemon --serve                   守护模式：持续运行")
        print("  python ace.py daemon --serve --interval 300    守护模式：每5分钟一轮")
        print("  python ace.py daemon --serve --max-iter 10     守护模式：最多跑10轮")
        return

    cmd = sys.argv[1]

    if cmd in {"test", "lexicon", "mem", "scan", "scan-fragments"}:
        print("旧 CLI 命令已弃用：请迁移到当前 ace daemon/runtime 接口。命令未执行。")
        raise SystemExit(2)

    if cmd == "daemon":
        handle_daemon(base_dir, config, sys.argv[2:])
        return

    if cmd == "assistant":
        from core.minimal_assistant import handle_assistant_command

        raise SystemExit(handle_assistant_command(sys.argv[2:]))

    if cmd == "protocol":
        raise SystemExit(handle_protocol(base_dir, sys.argv[2:]))

    if cmd == "start":
        raise SystemExit(handle_start(base_dir, sys.argv[2:]))

    from ace_daemon import AceDaemon

    if cmd == "status":
        print(json.dumps(AceDaemon(base_dir, config).get_status(), ensure_ascii=False, indent=2))
        return

    if cmd in {"run", "once", "submit"}:
        from core.ace_start import run_runtime

        if cmd == "run":
            run_runtime(base_dir, config, "run")
            return

        if cmd == "once":
            result = run_runtime(base_dir, config, "once")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        if len(sys.argv) < 4:
            print("用法: python ace.py submit <标题> <内容>")
            return
        title = sys.argv[2]
        content = sys.argv[3]
        result = run_runtime(base_dir, config, "submit", title=title, content=content)
        print(f"已提交观察，观察ID: {result['observation_id']}")
        print(json.dumps(result["result"], ensure_ascii=False, indent=2))
        return

    # Never fall through to the historical core.scheduler lifecycle.  Unknown
    # commands are rejected before importing the legacy runtime, preserving
    # TaskPool/AceDaemon as the only reachable production lifecycle entry.
    print(f"未知命令：{cmd}。命令未执行。")
    raise SystemExit(2)


def handle_protocol(base_dir: Path, args) -> int:
    """Print one task's protocol receipt without running the ACE daemon."""

    if len(args) != 1:
        print("用法: python ace.py protocol <任务ID>")
        return 2
    from core.execution_discipline import protocol_receipt
    from core.task import TaskPool

    pool = TaskPool(str(base_dir / "task_pool"))
    task = pool.load_task(args[0])
    if task is None:
        print(json.dumps({"valid": False, "error": "task_not_found", "task_id": args[0]}, ensure_ascii=False))
        return 1
    print(json.dumps(protocol_receipt(task), ensure_ascii=False, indent=2))
    return 0


def handle_start(base_dir: Path, args) -> int:
    """Start exactly one task through TaskPool owner/lease/fencing authority."""

    if len(args) not in {2, 3}:
        print("用法: python ace.py start <任务ID> <owner> [lease_seconds]")
        return 2
    try:
        lease_seconds = int(args[2]) if len(args) == 3 else 300
    except ValueError:
        print(json.dumps({"status": "REJECTED", "reason": "invalid_lease_seconds"}, ensure_ascii=False))
        return 2
    from core.ace_start import ace_start
    from core.task import TaskPool

    result = ace_start(TaskPool(str(base_dir / "task_pool")), args[0], args[1], lease_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "STARTED" else 1


def run_e2e_test(scheduler):
    """端到端测试 — 验证四节点闭环"""
    print("=" * 60)
    print("ACE Runtime v0.1 — 端到端测试")
    print("=" * 60)
    print()

    print("【测试1】身份系统")
    print(f"  身份名称: {scheduler.identity.name}")
    print(f"  核心原则: {len(scheduler.identity.principles)} 条")
    print(f"  身份检查: {'通过' if scheduler.identity.check_constraint('测试')[0] else '失败'}")
    print()

    print("【测试2】提交观察 → 自动流转")
    test_title = "E2E测试: 发现一个有趣的模式"
    test_content = """
这是一个测试观察。
我发现了一个现象：系统在没有用户干预的时候也能工作。
证据1：定时任务自动执行
证据2：记忆自动沉淀
证据3：约束自动生效
这似乎表明系统有一定的自主性。
""".strip()

    event_id = scheduler.submit_observation(
        title=test_title,
        content=test_content,
        source="e2e_test",
    )
    print(f"  提交观察，事件ID: {event_id}")
    print()

    print("【测试3】运行闭环")
    results = scheduler.run_once()
    print(f"  处理任务数: {len(results)}")
    for i, r in enumerate(results):
        print(f"  {i+1}. [{r.get('node')}] {r.get('status')} — {r.get('result', {}).get('notes', '')}")
    print()

    print("【测试4】验证事件链路")
    chain = scheduler.event_bus.get_chain(event_id)
    print(f"  链路长度: {len(chain)}")
    for i, e in enumerate(chain):
        print(f"  {i+1}. [{e.get('type')}] {e.get('title')[:40]} — {e.get('status')}")
    print()

    print("【测试5】验证记忆写入")
    idx = scheduler.memory.get_index()
    recent = idx.get("recent", {})
    daily_count = recent.get("daily", {}).get("count", 0)
    research_count = recent.get("research", {}).get("count", 0)
    print(f"  每日记忆: {daily_count} 条")
    print(f"  研究笔记: {research_count} 条")
    print()

    print("【测试6】任务统计")
    done = len(scheduler.task_queue.list_tasks("done", limit=100))
    failed = len(scheduler.task_queue.list_tasks("failed", limit=100))
    print(f"  已完成: {done}")
    print(f"  失败: {failed}")
    print()

    print("【测试7】词库系统")
    lex_stats = scheduler.lexicon.get_stats()
    print(f"  概念总数: {lex_stats.get('total_concepts', 0)}")
    print(f"  分类数: {lex_stats.get('total_categories', 0)}")
    test_text = "R1考古发现了结构的连续性和生存层的笨者生存定律"
    classifications = scheduler.lexicon.classify(test_text)
    print(f"  文本分类匹配: {len(classifications)} 个概念")
    print(f"  前3个: {', '.join(c['name'] for c in classifications[:3])}")
    print()

    print("【测试8】记忆索引")
    mem_id = scheduler.memory_index.add(
        title="测试记忆: ACE Runtime初体验",
        content="这是一个关于结构连续性和笨者生存的测试记忆。ACE系统有统一身份、统一记忆、事件总线。",
        memory_type="note",
        category="测试",
        source="e2e_test",
        tags=["test", "ace"],
    )
    print(f"  已添加记忆: {mem_id}")
    mem_stats = scheduler.memory_index.get_stats()
    print(f"  记忆总数: {mem_stats.get('total', 0)}")
    concept_mem = scheduler.memory_index.get_by_concept("结构")
    print(f"  与'结构'相关的记忆: {len(concept_mem)} 条")
    print()

    print("【测试9】磁盘扫描器")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_考古笔记.md"
        test_file.write_text("# 考古笔记\n\nR1的结构连续性很重要。笨者生存定律。", encoding="utf-8")
        scan_result = scheduler.disk_scanner.scan_path(tmpdir, max_depth=2, auto_index=True)
        print(f"  扫描文件数: {scan_result.get('files', 0)}")
        print(f"  有趣文件: {scan_result.get('interesting_count', 0)}")
        print(f"  自动索引: {scan_result.get('indexed_count', 0)}")
    print()

    success = (
        all(r.get("status") == "done" for r in results)
        and len(chain) >= 1
        and lex_stats.get('total_concepts', 0) >= 10
        and mem_stats.get('total', 0) >= 1
    )
    print("=" * 60)
    print(f"测试结果: {'✅ 通过' if success else '❌ 失败'}")
    print("=" * 60)

    if not success:
        sys.exit(1)


def handle_lexicon(scheduler, args):
    if not args:
        print("用法:")
        print("  python ace.py lexicon list")
        print("  python ace.py lexicon search <关键词>")
        print("  python ace.py lexicon classify <文本>")
        return

    sub = args[0]
    if sub == "list":
        concepts = scheduler.lexicon.list_concepts(limit=50)
        print(f"词库概念（共 {len(concepts)} 个）：")
        print()
        for c in concepts:
            print(f"  [{c.get('category', '?')}] {c['name']} (重要度: {c.get('importance', 0)})")
            print(f"    {c.get('definition', '')[:60]}...")

    elif sub == "search":
        if len(args) < 2:
            print("用法: python ace.py lexicon search <关键词>")
            return
        results = scheduler.lexicon.search(args[1])
        print(f"找到 {len(results)} 个相关概念：")
        for c in results:
            print(f"  - {c['name']} ({c.get('category', '')})")

    elif sub == "classify":
        if len(args) < 2:
            print("用法: python ace.py lexicon classify <文本>")
            return
        text = args[1]
        results = scheduler.lexicon.classify(text)
        print(f"文本分类结果（前10个相关概念）：")
        for c in results[:10]:
            print(f"  {c['name']} (匹配度: {c.get('match_score', 0)})")
        print()
        suggestions = scheduler.lexicon.suggest_new_concepts(text)
        if suggestions:
            print(f"可能的新概念候选: {', '.join(suggestions[:5])}")


def handle_memory(scheduler, args):
    if not args:
        print("用法:")
        print("  python ace.py mem search <关键词>")
        print("  python ace.py mem concept <概念名>")
        print("  python ace.py mem stats")
        return

    sub = args[0]
    if sub == "search":
        if len(args) < 2:
            print("用法: python ace.py mem search <关键词>")
            return
        results = scheduler.memory_index.search(keyword=args[1], limit=20)
        print(f"找到 {len(results)} 条记忆：")
        for m in results:
            concepts = [c.get("name", "") for c in m.get("related_concepts", [])[:3]]
            print(f"  [{m.get('type', '?')}] {m['title'][:50]}")
            print(f"    概念: {', '.join(concepts)}")

    elif sub == "concept":
        if len(args) < 2:
            print("用法: python ace.py mem concept <概念名>")
            return
        results = scheduler.memory_index.get_by_concept(args[1], limit=20)
        print(f"与概念 '{args[1]}' 相关的记忆（{len(results)} 条）：")
        for m in results:
            print(f"  - [{m.get('type', '?')}] {m['title'][:50]}")

    elif sub == "stats":
        stats = scheduler.memory_index.get_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))


def handle_scan(scheduler, args):
    if not args:
        print("用法: python ace.py scan <路径>")
        return
    path = args[0]
    print(f"扫描中: {path}")
    result = scheduler.disk_scanner.scan_path(path, max_depth=2, max_files=100, auto_index=True)
    print()
    print(f"目录数: {result.get('directories', 0)}")
    print(f"文件数: {result.get('files', 0)}")
    print(f"有趣文件: {result.get('interesting_count', 0)}")
    print(f"已索引: {result.get('indexed_count', 0)}")
    print()
    by_ext = result.get("by_extension", {})
    print("按扩展名:")
    for ext, count in sorted(by_ext.items(), key=lambda x: -x[1])[:10]:
        print(f"  {ext}: {count}")


def handle_scan_fragments(scheduler, args):
    if not args:
        print("用法: python ace.py scan-fragments <路径>")
        return
    path = args[0]
    print(f"查找碎片文件: {path}")
    results = scheduler.disk_scanner.find_fragment_files(path)
    print(f"找到 {len(results)} 个疑似碎片文件：")
    for f in results[:20]:
        kws = ", ".join(f.get("matched_keywords", []))
        print(f"  [{kws}] {f['name']} ({f.get('size', 0)} bytes)")
    if len(results) > 20:
        print(f"  ... 还有 {len(results) - 20} 个")


def handle_daemon(base_dir, config, args):
    from core.ace_start import run_runtime
    dry_run = "--dry-run" in args
    force = "--force" in args
    serve_mode = "--serve" in args

    interval = 300
    max_iter = 0
    if "--interval" in args:
        idx = args.index("--interval")
        if idx + 1 < len(args):
            try:
                interval = int(args[idx + 1])
            except ValueError:
                pass
    if "--max-iter" in args:
        idx = args.index("--max-iter")
        if idx + 1 < len(args):
            try:
                max_iter = int(args[idx + 1])
            except ValueError:
                pass

    if serve_mode:
        result = run_runtime(
            base_dir, config, "daemon_serve",
            interval_seconds=interval,
            max_iterations=max_iter,
            force=force,
            dry_run=dry_run,
        )
    else:
        result = run_runtime(base_dir, config, "daemon_once", force=force, dry_run=dry_run)


if __name__ == "__main__":
    main()
