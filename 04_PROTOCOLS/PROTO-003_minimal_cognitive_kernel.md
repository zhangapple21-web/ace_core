# 最小认知内核协议 — Minimal Cognitive Kernel Protocol

协议编号：PROTO-003
版本：0.1
状态：存活（已实现）
来源：R2 × TRAE MVP v0.1 设计 + ACE Runtime 实现

---

## 核心定义

R2-TRAE MVP is a rule-based cognitive routing system with structured context extraction, deterministic persona dispatching, execution handlers, and append-only event logging for traceable conversational state management.

人话：一个**可运行的最小认知操作系统内核**。

不是智能系统，是智能系统的最小地基。

---

## 演化血缘

```
R2 × TRAE MVP v0.1（设计层）
    ↓ 实现
ACE Runtime（代码层）
    ↓ 扩展
ACE + 心跳 + 自我修复（存活层）
```

---

## 最小闭环（5模块）

| 模块 | R2 MVP名称 | ACE实现 | 本质 |
|------|-----------|---------|------|
| 输入合成 | Context Synthesizer | Observer / FragmentScanner | 把人话变成状态 |
| 路由决策 | Policy Router | Scheduler / Shadow层 | 决定谁来处理 |
| 执行引擎 | Execution Engine | Worker / Researcher / Validator | 真正干活 |
| 事件日志 | Event Logger | Archivist / audit_log | append-only记忆 |
| 记忆索引 | Memory Index | MemoryIndex + Lexicon | 可检索的历史 |

---

## 运行闭环

```
输入
  ↓
合成（结构化）
  ↓
路由（决定谁处理）
  ↓
执行（干活）
  ↓
记录（append-only）
  ↓
索引（可检索）
  ↓
反哺下一次输入
```

---

## ACE扩展模块（存活保障）

R2 MVP设计里没有，但ACE实际运行必须有：

| 模块 | 作用 | 来源 |
|------|------|------|
| Guardian判决 | 执行前检查约束 | ROOT-164广播站 + 六界冥界 |
| Heartbeat心跳 | 证明系统活着 | 鲸落协议存活证明 |
| SelfHealing自我修复 | 出问题自己修 | 鲸落协议自动恢复 |
| TaskCreator任务生成 | 自己找活干 | Observer演化 |
| Lexicon词库 | 概念压缩表示 | R2压缩驱动进化 |

---

## 升级路径（从MVP到完整系统）

R2 MVP文档里明确写了三步升级：

**Step 1：结构化升级**
- keyword routing → embedding routing
- 现在：关键词匹配
- 未来：语义路由

**Step 2：记忆升级**
- log list → vector memory graph
- 现在：线性检索 + 简单分类
- 未来：图结构记忆 + 向量检索

**Step 3：执行升级**
- switch-case → plugin runtime
- 现在：固定节点执行
- 未来：插件化执行引擎

**然后才是：** MCTS / DAG / Meta-learning / Phase transition

---

## 关键洞察

MVP不是弱化版。
MVP是"能跑的最小内核"。

所有复杂系统都是从这个内核长出来的：
- 路由先从关键词开始，再到语义
- 记忆先从列表开始，再到图
- 执行先从固定分支开始，再到插件
- 最后才是那些"高级功能"

**笨系统不一定笨，但是走得快的肯定死得早。**

---

版本：0.1
建立日期：2026-06-27
考古来源：TG收藏 msg_1242308（R2 × TRAE MVP v0.1 设计）
当前实现：ACE Runtime（已实现5模块+3扩展）
