#!/usr/bin/env python3
"""跨机器 CI 护栏：验证 ACE 本轮修复的持久状态是否落地。

用法（仓库根目录任意位置）：
    python ops/verify_fixes.py

不依赖 C:\\tmp 这类本机绝对路径；全部路径由脚本位置推导。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

POOL = ROOT / "task_pool"
FREEZONE = ROOT / "task_pool_freezone"

print("=== 自动化验证开始 ===")

# 1. 账本漂移修复：代码层面 _transition 内包裹 _ledger_open/_ledger_close
print("\n1. 检查账本漂移修复代码...")
task_py = (ROOT / "core" / "task.py").read_text(encoding="utf-8")
assert "_ledger_open(task)" in task_py and "_ledger_close(" in task_py and "transition:" in task_py
print("   _transition 中已包裹 _ledger_open/_ledger_close: PASSED")

# 2. hold 计数器
print("\n2. 检查 hold 计数器...")
from core.task_ledger import LEDGER_COUNTERS
assert "hold" in LEDGER_COUNTERS, "LEDGER_COUNTERS 缺少 hold"
print("   PASSED")

# 2b. 归档知识复用的接线仍然在位（连续性护栏）
# 这套读取器与交付阶段长在 ace_daemon.py 的同一段代码里。共享树上若有人拿旧
# 快照整文件覆盖 ace_daemon.py，接线会被静默抹掉，而分散在各测试文件里的用例
# 可能完全不被运行。文本断言足够便宜，且不 import（避免副作用）。
print("\n2b. 检查归档知识复用接线...")
daemon_src = (ROOT / "ace_daemon.py").read_text(encoding="utf-8")
for _marker in ("_run_knowledge_reuse_stage", "_write_knowledge_reuse_report",
                "_record_reuse_contributions", "_reuse_hint_for",
                "KnowledgeReuseGate"):
    assert _marker in daemon_src, f"ace_daemon.py 缺少归档知识复用接线: {_marker}"
reuse_src = (ROOT / "core" / "knowledge_reuse.py").read_text(encoding="utf-8")
assert "artifact_contributions" in reuse_src, "core/knowledge_reuse.py 缺少交付溯源核算"
roles_src = (ROOT / "core" / "task_roles.py").read_text(encoding="utf-8")
assert "JOIN_SOURCE_PREFIX" in roles_src and "_is_reuse_pointer" in roles_src, (
    "core/task_roles.py 缺少复用指针不计入证据的护栏"
)
print("   PASSED")

# 3. 索引文件
print("\n3. 检查任务索引...")
index_path = POOL / "task_index.json"
if index_path.exists():
    idx = json.loads(index_path.read_text(encoding="utf-8"))
    print(f"   索引版本: {idx.get('version')}, 任务数: {len(idx.get('tasks', {}))}")
    print("   PASSED")
else:
    print("   SKIPPED (will be created on first daemon run)")

# 4. 执行纪律序列化
print("\n4. 验证执行纪律序列化...")
from core.execution_discipline import build_execution_discipline, ExecutionDiscipline
from core.task import Task
env = build_execution_discipline(
    title="Auto Test", hypothesis="Test", priority="high",
    tags=["auto"], depends_on=[],
    admission={"expected_result": "r", "verification_method": "v", "risk": "low"},
)
task = Task(task_id="RQ-AUTO-001", title="Auto Test", priority="high")
task.outputs = {"execution_discipline": env.to_dict()}
data = json.loads(json.dumps(task.to_dict(), ensure_ascii=False))
task2 = Task.from_dict(data)
assert "execution_discipline" in task2.outputs
assert task2.outputs["execution_discipline"]["complexity"] == "simple"
print("   PASSED")

# 5. 语义去重
print("\n5. 验证语义去重...")
from core.task_admission import duplicate_task
adm1 = {"source_type": "archaeology", "source_ref": "file.json", "why_now": "reason A",
        "expected_result": "result A", "verification_method": "method A", "evidence": []}
adm2 = {"source_type": "archaeology", "source_ref": "file.json", "why_now": "reason B",
        "expected_result": "result B", "verification_method": "method B", "evidence": []}
tasks = [Task(task_id="RQ-001", title="T1", priority="medium", outputs={"admission": adm1})]
assert duplicate_task(tasks, adm2) is None, "语义字段不同应视为不同任务"
print("   PASSED")

# 6. 多源去重
print("\n6. 验证多源去重...")
from core.worker_capsule import _envelope_of
task3 = Task(task_id="RQ-002", title="T2")
task3.outputs = {"execution_discipline": build_execution_discipline(
    title="T2", hypothesis="", priority="medium", tags=[], depends_on=[],
    admission={"evidence": [{"content": "fact1", "source": "srcA"},
                             {"content": "fact1", "source": "srcB"}]},
).to_dict()}
env3 = _envelope_of(task3)
known = env3.get("clarification", {}).get("known_facts", [])
sources = set()
for k in known:
    if isinstance(k, dict):
        sources.add(k.get("source", ""))
print(f"   保留的 source: {sources}")
assert "srcA" in sources and "srcB" in sources, "多源去重失败"
print("   PASSED")

# 7. ace_capsule 池面校验（host-adapter-lab 位于工作区旁，可选）
print("\n7. 验证 ace_capsule 池面校验...")
lab = ROOT.parent / "ace-host-adapter-lab"
ace_capsule_py = lab / "ace_capsule.py"
if ace_capsule_py.exists():
    sys.path.insert(0, str(lab))
    from ace_capsule import pool_dir
    from bridge_config import get_config
    cfg = get_config()
    with tempfile.TemporaryDirectory() as tmp:
        p = pool_dir({"pool": "scratch", "scratch_name": "test123"}, cfg)
        print(f"   生成路径: {p}")
        temp_root = Path(tempfile.gettempdir()).resolve()
        assert temp_root in p.parents or p == temp_root / "ace-pi-bridge" / "test123"
    print("   PASSED")
else:
    print("   SKIPPED (ace-host-adapter-lab 不在工作区旁)")

# 8. Free Zone 独立池
print("\n8. 检查 Free Zone 独立池...")
if FREEZONE.exists():
    print(f"   目录存在: {FREEZONE}")
else:
    print("   目录将在 daemon 首次运行时自动创建")
print("   PASSED")

# 9. 意志层与交付门
print("\n9. 验证意志层与交付门...")
from core.delivery_execution import (
    REASON_MISSING,
    REASON_OK,
    DeliveryExecutor,
    declares_delivery,
    delivery_contract,
    verify_delivery,
)
from core.task import TaskPool

assert hasattr(TaskPool, "reopen_task"), "缺少 TaskPool.reopen_task（外部新证据逃生口）"

probe = Task(task_id="RQ-AUTO-DELIVERY", title="probe", priority="low")
probe.outputs = {
    "delivery": {
        "required_path": "docs/VERIFY_FIXES_PROBE.md",
        "success_metric": "file_exists_nonempty",
        "domain": "document",
    }
}
assert declares_delivery(probe), "声明了 delivery 的任务应被识别"
assert delivery_contract(probe)["valid"], "合法交付契约应通过校验"

with tempfile.TemporaryDirectory() as tmp:
    workspace = Path(tmp)
    assert verify_delivery(probe, workspace)["reason"] == REASON_MISSING, "缺文件必须报缺失"
    artifact = workspace / "docs" / "VERIFY_FIXES_PROBE.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("# probe\n", encoding="utf-8")
    receipt = verify_delivery(probe, workspace)
    assert receipt["reason"] == REASON_OK and receipt["content_sha256"], "已落盘产物必须通过并给出内容哈希"
    # 谎报成功的 worker 不能伪造回执（用一条尚无产物的新契约）
    liar = Task(task_id="RQ-AUTO-DELIVERY-LIAR", title="probe", priority="low")
    liar.outputs = {
        "delivery": {
            "required_path": "docs/VERIFY_FIXES_LIAR.md",
            "success_metric": "file_exists_nonempty",
            "domain": "document",
        }
    }
    lied = DeliveryExecutor(workspace, worker_runner=lambda **_: {"ok": True}).execute(liar)
    assert lied["status"] == "WORKER_FAILED", "回执必须来自磁盘，不采信 worker 自报"
    assert DeliveryExecutor(workspace).execute(liar)["status"] == "NO_WORKER_AVAILABLE", "无 worker 必须失败关闭"
    # bool(mapping) is always True, so a self-reporting failure must not be
    # recorded as ok: true. This is the exact shape OpenCodeWorker returns.
    failed_report = DeliveryExecutor(
        workspace, worker_runner=lambda **_: {"success": False, "error": "opencode_all_models_failed"}
    ).execute(liar)
    assert failed_report["attempts"][0]["ok"] is False, "worker 自报失败必须如实记录，不得被 bool(dict) 粉饰"

# The CLI is NOT on PATH but IS installed, and OpenCodeWorker resolves it by
# absolute default. Assert the resolved worker is real, so the earlier belief
# "no worker exists here" cannot quietly come back and silently disable delivery.
from core.opencode_worker import OpenCodeWorker as _RealWorker  # noqa: E402

_worker = _RealWorker()
assert Path(_worker.executable).exists(), (
    f"交付 worker 不可用: {_worker.executable} 不存在。file_exists_nonempty 意志会永远停在 delivery_not_produced"
)
print(f"   交付 worker: {_worker.executable}")

# The intent layer must be reachable from the real runtime, not only from a CLI
# someone has to remember to run. And it must be wired to a real moment with a
# once-a-day gate, never to a bare cron that hard-feeds the pool.
sys.path.insert(0, str(ROOT / "ops"))
import daily_intent_scheduler as intent_pool  # noqa: E402
from ace_daemon import AceDaemon as _Daemon  # noqa: E402

assert hasattr(_Daemon, "_run_intent_pool_if_due"), "意志层必须挂进 daemon 的真实时机，否则永远不会被调用"
_src = (ROOT / "ace_daemon.py").read_text(encoding="utf-8")
assert "_run_intent_pool_if_due()" in _src, "意志触发点必须真的被 cycle 调用"
assert "cron" not in _src.lower().split("def _run_intent_pool_if_due")[1][:1200], (
    "意志层不得绑定裸 cron 硬喂"
)
print("   意志触发点: 已挂入 daemon cycle（每日一次 + 班次门）")

# A consumed will must never reopen, no matter how often the pool is assessed.
# The state file and the live pool disagreed once already and the intent read
# back as `candidate`, which put 10 duplicate `injected` entries into the record.
_pool_probe = TaskPool(str(ROOT / "task_pool"))
_intents = intent_pool.load_queue(ROOT / "intents" / "daily_queue.jsonl")
_intent_state = intent_pool.load_state(ROOT / "intents" / "intent_state.json")
_report = intent_pool.assess(_pool_probe, _intents, 3, _intent_state)
assert intent_pool.decide(_report)["outcome"] != "INJECT" or _report["in_flight"] < 3, "粮仓判定必须自洽"
_archived_reopened = [
    item["intent_id"]
    for item in _report["evaluated"]
    if (item.get("task") or {}).get("status") == "archived" and item.get("eligible")
]
assert not _archived_reopened, f"已归档且已交付的意志被重开: {_archived_reopened}"
# and the demotion guard itself
_guard = {"protocol": intent_pool.PROTOCOL, "intents": {"probe": {"state": "fulfilled", "task_id": "RQ-1"}}}
intent_pool.record_observations(
    _guard,
    {
        "evaluated": [
            {
                "intent_id": "probe",
                "question": "q",
                "state": "candidate",
                "state_reason": "no_task_created_yet",
                "task": None,
                "errors": None,
            }
        ]
    },
)
assert _guard["intents"]["probe"]["state"] == "fulfilled", "陈旧观察不得把 fulfilled 降级回 candidate"
assert _guard["intents"]["probe"]["task_id"] == "RQ-1", "唯一的 task 指针不得被空观察抹掉"
print("   意志防重注: 已归档不可重开 + 状态不可降级")

queue_path = ROOT / "intents" / "daily_queue.jsonl"
if queue_path.exists():
    queue = intent_pool.load_queue(queue_path)
    assert queue, "意志粮仓不应为空"
    for intent in queue:
        errors = intent_pool.validate_intent(intent)
        assert not errors, f"{intent.get('intent_id')} 字段不合法: {errors}"
    print(f"   意志池: {len(queue)} 条，全部字段合法")
else:
    print("   SKIPPED (intents/daily_queue.jsonl 尚未创建)")

assert (ROOT / "docs" / "INTENT_DELIVERY_PROTOCOL.md").exists(), "缺少意志层协议文档"
print("   PASSED")

print("\n=== 所有自动化验证通过 ===")
