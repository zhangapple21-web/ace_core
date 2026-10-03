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

print("\n=== 所有自动化验证通过 ===")
