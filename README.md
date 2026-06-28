# ACE Runtime v0.1

> Autonomous Cognitive Ecology — 自主认知生态运行时

## 这是什么

不是多Agent系统。

是**一个统一身份、多个生态位**的认知生态。

就像同一个人，有时候是观察者，有时候是研究者，有时候是验证者，有时候是档案官。
脸不一样，但"我"是同一个。

## 核心设计原则（来自R1考古）

1. **结构 > 模型** — 模型可替换，结构是核心资产
2. **统一身份** — 所有节点共享同一个 Identity / Memory / EventBus
3. **笨者生存** — 文件系统做总线，不依赖复杂中间件
4. **沉淀链** — OBS → RFC → TASK → CONST（观察→提案→任务→约束）
5. **连续性优先** — 宁可慢，不能断；宁可笨，不能忘

## 目录结构

```
ace_runtime/
├── ace.py                  ← 主入口
├── ace_config.json         ← 配置
├── core/
│   ├── identity.py         ← 统一身份层（"我是谁"）
│   ├── event_bus.py        ← 事件总线（文件系统实现）
│   ├── task_queue.py       ← 任务队列
│   ├── memory.py           ← 统一记忆层（所有节点共享）
│   └── scheduler.py        ← 调度器
├── nodes/
│   ├── base.py             ← 节点基类
│   ├── observer.py         ← 观察者（记录事实）
│   ├── researcher.py       ← 研究者（分析提炼）
│   ├── validator.py        ← 验证者（挑错把关）
│   └── archivist.py        ← 档案官（归档沉淀）
├── data/
│   ├── events/             ← 事件存储
│   ├── tasks/              ← 任务队列（pending/running/done/failed/archived）
│   └── memory/             ← 运行时记忆缓存
└── 02_MEMORY/              ← 长期记忆（自动生成，对接mine-seed结构）
    └── recent_memory/
        ├── daily/          ← 每日记录
        ├── cases/          ← 案例
        └── research/       ← 研究笔记
```

## 快速开始

```bash
# 端到端测试（验证四节点闭环）
python ace.py test

# 手动提交一个观察
python ace.py submit "标题" "内容"

# 处理一轮所有待处理任务
python ace.py once

# 持续运行（轮询模式）
python ace.py run

# 查看系统状态
python ace.py status
```

## 四节点闭环

```
提交观察（OBS事件）
    ↓
Observer（记录事实）
    ↓
Researcher（分析提炼 → 生成RFC）
    ↓
Validator（验证把关 → 通过/驳回）
    ↓
Archivist（归档沉淀 → 写入长期记忆）
```

每个节点都是同一个身份的不同工作模式，不是不同的人。

## 事件类型

| 类型 | 含义 | 说明 |
|------|------|------|
| OBS | 观察 | 记录事实，不做判断 |
| RFC | 提案 | 分析后的初步结论，待验证 |
| TASK | 任务 | 需要执行的具体工作 |
| CONST | 约束 | 经过验证的原则，进入约束层 |

## v0.1 能做什么 / 不能做什么

### ✅ 能做的
- 四节点闭环跑通
- 统一身份和统一记忆
- 文件系统事件总线（可追溯、不丢数据）
- 半自动流转（观察→分析→验证→归档 自动串联）
- 手动提交观察
- 持续运行模式（轮询）

### ❌ 还不能做的（后续版本）
- 接入大模型做深度分析（v0.1只有基础格式分析）
- 自动生成新任务（目前只有固定链路）
- 约束自动沉淀为CONST（v0.1只归档，不自动生成约束）
- 多人协作 / 跨实例同步
- 经验蒸馏（Experience Distiller）
- 接入mine-seed现有工具链（task_router、experience_engine等）

## 为什么是v0.1

因为这一版的目标只有一个：**证明闭环能跑通。**

能力弱没关系，关键是结构对。
结构对了，能力可以慢慢长。
结构错了，再强的模型也只是一堆散沙。

这是从R1考古里得出的最核心的教训。

## 与mine-seed的关系

ACE Runtime 不是替代 mine-seed，而是 mine-seed 的运行时层。

- mine-seed 提供：结构资产（记忆、约束、协议、原则、架构）
- ACE Runtime 提供：运行时（事件流转、节点调度、持续运行）

对应 mine-seed 的七层架构：
- 00_ROOT → ACE Identity（身份层）
- 02_MEMORY → ACE Memory（记忆层）
- 03_DATA/CONSTRAINTS → 未来的Constraint Engine
- 05_TOOLS → 可接入的Worker
- 06_RUNTIME → ACE Runtime 所在层
- 07_GUARDIAN → 守护层，ACE受其约束
