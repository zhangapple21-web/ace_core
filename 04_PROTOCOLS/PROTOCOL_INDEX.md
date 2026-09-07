# 协议谱系总览

## 定义

协议不是规则。
协议是系统各部分之间的"约定"——约定好了怎么说话、怎么协作、怎么不互相打起来。

没有协议，系统就是一堆零件。
有了协议，零件才能拼成一个活着的东西。

---

## 协议演化谱系

```
老张164锚点（祖先层）
├── SIP-164 守魂者协议
├── ROOT-164 广播站协议
├── 方舟ARK 双脑备份协议
├── 鲸落协议（死亡恢复）
├── 六界并行协议
└── 宇宙主循环协议
    ↓ 演化
ACE Runtime（当前层）
├── 零号原则（身份协议）
├── 任务生命周期协议
├── 节点协作协议
├── Guardian判决协议
├── 记忆索引协议
├── 词库演化协议
├── 心跳协议
└── 自我修复协议
```

---

## 各协议说明

### 001 — 身份协议（Identity Protocol）
- 来源：SIP-164守魂者 + ROOT-164广播站
- 核心：系统只对老张一人负责
- 现状：存活，实现于identity.py + PRINCIPLES.md
- 版本：0.2

### 002 — 存活协议（Survival Protocol）
- 来源：鲸落协议 + 方舟ARK双脑备份
- 核心：心跳 + 自我修复，活着是第一优先级
- 现状：存活，实现于heartbeat.py + self_healing.py
- 版本：0.1（新建）

### 003 — 最小认知内核协议（Minimal Cognitive Kernel Protocol）
- 来源：R2 × TRAE MVP v0.1 设计
- 核心：5模块闭环（输入→路由→执行→记录→索引）
- 现状：存活，实现于ace_runtime整体
- 版本：0.1

### 004 — 任务生命周期协议（Task Lifecycle Protocol）
- 来源：六界并行 + 宇宙主循环
- 核心：pending → active → blocked → review → approved → archived
- 现状：存活，实现于task.py
- 版本：1.0

### 005 — 节点协作协议（Node Collaboration Protocol）
- 来源：六界系统
- 核心：Observer/Researcher/Validator/Archivist/Guardian 五节点闭环
- 现状：存活，实现于task_roles.py
- 版本：1.0

### 006 — Guardian判决协议（Guardian Verdict Protocol）
- 来源：ROOT-164广播站约束
- 核心：每次执行前检查约束，不通过就拒绝
- 现状：存活，实现于task_roles.py Guardian类
- 版本：0.9

### 007 — 记忆索引协议（Memory Index Protocol）
- 来源：冥界深度存储 + SIP-164灵魂坐标
- 核心：append-only，可追溯，结构化索引
- 现状：存活，实现于memory_index.py
- 版本：0.5

### 008 — 词库演化协议（Lexicon Evolution Protocol）
- 来源：概念压缩 + 经验沉积
- 核心：概念从经验中提炼，词库自动生长
- 现状：存活，实现于lexicon.py
- 版本：0.8

### 009 — 外部 Agent Runtime 适配边界协议（External Runtime Adaptation Boundary）
- 来源：外部 Agent Workflow/Runtime 评估经验（首个实例：oh-my-codex）
- 核心：先核验源码/版本/能力，再做机制映射；外部运行时不得取得 ACE 权威或建立第二事实源
- 现状：存活，规范正文见 `docs/EXTERNAL_RUNTIME_ADAPTATION_BOUNDARY_v1.md`，实例登记见 `docs/external_runtime_adaptation_register.jsonl`
- 版本：1.0

### 010 — 执行纪律协议（Execution Discipline Protocol）
- 来源：OMX-inspired Free Zone Pilot（`OMX-INSPIRED-FZ-20260905`）与 ACE 现有任务生命周期
- 核心：复杂任务先记录澄清、最小计划、验证边界与停止条件；简单任务走轻量分支；不把未验证的并行、独立审查或恢复语义伪装成能力；所有任务共享八阶段开工流水线和有限证据账本
- 现状：存活，实现于 `core/execution_discipline.py`，由 `TaskPool.create_task` 与既有生命周期事件接入；正文见 `docs/ACE_START_PROTOCOL_V2.md`
- 版本：1.1 / 开工协议 v2

---

## 协议状态

- 存活协议：10个
- 死亡协议：0个
- 新建协议：5个（存活协议、最小认知内核、词库演化、外部 Runtime 适配边界、执行纪律）

---

版本：0.2.0
建立日期：2026-06-27
更新日期：2026-09-05
来源：老张164锚点考古 + R2 MVP设计考古 + ACE代码结构对齐
