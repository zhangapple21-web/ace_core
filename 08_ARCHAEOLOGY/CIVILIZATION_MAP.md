# ACE 文明地图 — 2026-06-29

**版本**：v0.1
**目标**：定义 R2 Phase-2：Civilization Convergence

---

## 一、文明分层架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL LAYER（外部）                              │
│                                                                             │
│   User Input → Task → Response → Feedback                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        OBSERVATION LAYER（感知）                             │
│                                                                             │
│   FileScanner │ Git考古 │ WebSearch │ MemoryRead │ BinarySense            │
│                                                                             │
│   职责：看到，不判断                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        RESEARCH LAYER（研究）                               │
│                                                                             │
│   Researcher │ ConceptMiner │ HypothesisTree │ EvidenceCollector            │
│                                                                             │
│   职责：从观察到理解，从数据到信息                                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        VALIDATION LAYER（验证）                             │
│                                                                             │
│   Validator │ EvidenceRegistry │ ContractEnforcer                         │
│                                                                             │
│   职责：判断真假，不是判断价值                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        GOVERNOR LAYER（治理）                               │
│                                                                             │
│   KnowledgeGovernor │ RepositoryGovernor │ Revision │ RejectionEngine      │
│                                                                             │
│   职责：判断是否进入文明，决定去哪里                                         │
│                                                                             │
│   ⚠️ 问题：角色爆炸，需要收敛                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CIVILIZATION LAYER（文明核心）                        │
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│   │ Lexicon     │  │ Experience   │  │ Constraint  │  │ Protocol    │     │
│   │ 词汇体系     │  │ 经验库       │  │ 约束体系     │  │ 协议体系     │     │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                                             │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│   │ Pattern     │  │ Principle   │  │ Law         │  │ Paradigm    │     │
│   │ 模式库       │  │ 原则库       │  │ 定律库       │  │ 范式库       │     │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘     │
│                                                                             │
│   职责：文明资产，可继承、可演化                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EVOLUTION LAYER（演化）                               │
│                                                                             │
│   EvolutionPlanner │ Lifecycle │ Mengpo │ Fitness                         │
│                                                                             │
│   职责：规划方向，管理生命周期，评估健康度                                    │
│                                                                             │
│   ⚠️ 问题：Mengpo 需要升级（Sleep/Wake/Archive/Rebirth）                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PUBLICATION LAYER（发布）                            │
│                                                                             │
│   Repository │ Archive │ Shadow │ PublicationContract                      │
│                                                                             │
│   职责：文明输出，沉淀到外部仓库                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、现有模块定位

### OBSERVATION LAYER

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| FileScanner | ✅ 活跃 | `core/observation/` | 扫描文件系统 |
| GitArchaeology | ✅ 活跃 | `core/observation/` | Git 历史考古 |
| WebSearch | ✅ 活跃 | `core/tools/` | 网页搜索 |
| BinarySense | ⚠️ 暂停 | `core/binary_sense/` | **停止考古，开始分析** |

**无位置模块**：无

---

### RESEARCH LAYER

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| Researcher | ✅ 活跃 | `core/research/` | 研究节点 |
| ConceptMiner | ✅ 活跃 | `core/research/` | 概念提取 |
| HypothesisTree | ✅ 活跃 | `core/research/` | 假设树 |
| EvidenceCollector | ✅ 活跃 | `core/research/` | 证据收集 |

**无位置模块**：无

---

### VALIDATION LAYER

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| Validator | ✅ 活跃 | `core/validation/` | 验证节点 |
| EvidenceRegistry | ✅ 活跃 | `core/governance/` | 证据登记 |
| ContractEnforcer | ✅ 活跃 | `core/governance/` | 契约执行 |

**无位置模块**：无

---

### GOVERNOR LAYER ⚠️ 需要收敛

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| KnowledgeGovernor | ✅ 活跃 | `core/governance/` | 知识馆长 |
| RepositoryGovernor | ✅ 活跃 | `core/governance/` | 仓库治理 |
| Revision | ✅ 活跃 | `core/governance/` | 知识修订 |
| RejectionEngine | 🆕 新增 | `core/governance/` | 拒绝引擎 |

**需要删除/合并的角色**：

| 原模块 | 问题 | 建议 |
|--------|------|------|
| Admission（准入） | 只是 Governor 的一个方法 | 合并到 Governor |
| Curator（馆长） | 与 KnowledgeGovernor 重复 | 删除 |
| Archivist（档案馆长） | 与 Repository 重复 | 删除 |
| Evolution（演化） | 只是状态，不是角色 | 合并到 EvolutionLayer |

---

### CIVILIZATION LAYER（文明核心）

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| Lexicon | ✅ 活跃 | `core/knowledge/` | 词汇体系 |
| Experience | ✅ 活跃 | `core/knowledge/` | 经验库 |
| Constraint | ✅ 活跃 | `core/knowledge/` | 约束体系 |
| Protocol | ✅ 活跃 | `core/knowledge/` | 协议体系 |
| Pattern | ✅ 活跃 | `core/knowledge/` | 模式库 |
| Principle | ✅ 活跃 | `core/knowledge/` | 原则库 |
| Law | ⚠️ 缺失 | — | **需要新增** |
| Paradigm | ⚠️ 缺失 | — | **需要新增** |

**需要重组的资产**：

```
Experience + Pattern + Evidence
        ↓ 蒸馏
    Principle
        ↓ 验证
    Law
        ↓ 跨领域
    Paradigm
```

---

### EVOLUTION LAYER

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| EvolutionPlanner | 🆕 新增 | `core/governance/` | 演化规划器 |
| Lifecycle | ✅ 活跃 | `core/governance/` | 生命周期 |
| Mengpo | ✅ 活跃 | `core/governance/` | 遗忘机制 |
| Fitness | ⚠️ 缺失 | — | **需要新增** |

**Mengpo 升级建议**：

```
Mengpo.v1
    │
    ├── Forget（遗忘）
    │
    └── Mengpo.v2（新增）
            │
            ├── Sleep（睡眠：暂时不活跃，但可唤醒）
            ├── Wake（唤醒：从睡眠恢复）
            ├── Archive（归档：长期存储，检索成本高）
            └── Rebirth（重生：从归档中提取，变成新知识）
```

---

### PUBLICATION LAYER

| 模块 | 状态 | 位置 | 备注 |
|------|------|------|------|
| Repository | ✅ 活跃 | `core/publication/` | 仓库管理 |
| Archive | ✅ 活跃 | `core/publication/` | 归档 |
| Shadow | ✅ 活跃 | `core/publication/` | 影子存档 |
| PublicationContract | ✅ 活跃 | `core/governance/` | 发布契约 |

**无位置模块**：无

---

## 三、Runtime 与 Civilization 分离

```
ACE/
├── CIVILIZATION/                    # 文明（不可删）
│   ├── knowledge/                  # 知识资产
│   │   ├── lexicon/                # 词汇体系
│   │   ├── experience/            # 经验库
│   │   ├── constraint/            # 约束体系
│   │   ├── protocol/              # 协议体系
│   │   ├── pattern/               # 模式库
│   │   └── principle/             # 原则库
│   ├── governance/                # 治理层
│   │   ├── governor/              # 馆长
│   │   ├── evolution/             # 演化
│   │   ├── lifecycle/             # 生命周期
│   │   ├── mengpo/                # 遗忘机制
│   │   ├── contract/              # 契约
│   │   └── evidence/             # 证据
│   ├── repository/                # 仓库
│   └── publication/               # 发布
│
└── RUNTIME/                        # 运行时（可删）
    ├── tools/                      # 工具集
    ├── workers/                    # 工作器
    ├── scheduler/                  # 调度器
    ├── models/                    # 模型
    ├── mcp/                        # MCP集成
    └── llm/                        # LLM客户端
```

**原则**：
- Runtime 可以全部删
- Civilization 不能删
- Runtime 死了可以重建， Civilization 死了文明就没了

---

## 四、角色收敛

### 当前问题

```
Researcher     ← 行为，不是角色
Validator      ← 行为，不是角色
Governor       ← 角色
Curator        ← 与 Governor 重复
Archivist      ← 与 Repository 重复
Revision       ← 行为，不是角色
Evolution      ← 状态，不是角色
Admission      ← 行为，不是角色
Rejector       ← 行为，不是角色
Planner        ← 行为，不是角色
```

### 收敛后

| 角色 | 职责 | 行为 |
|------|------|------|
| **Governor** | 决策 | Research(), Validate(), Admit(), Reject(), Review(), Publish() |
| **Evolution** | 演化 | Plan(), Assess(), Evolve() |
| **Memory** | 记忆 | Store(), Retrieve(), Distill(), Forget() |
| **Publication** | 发布 | Archive(), Sync(), Export() |

**原则**：
- 角色 = 持久的实体
- 行为 = 角色的方法
- 状态 ≠ 角色

---

## 五、Contract 升级

### 当前问题

Contract 现在越来越像**权限系统**（Python 代码）。

### 升级方向

Contract 应该变成**文明法律**。

```
Contract.v1（代码权限）
    │
    └── Contract.v2（文明法律）
            │
            ├── EvidenceContract
            │       任何 Hypothesis 不得直接成为 Fact
            │
            ├── KnowledgeContract
            │       任何知识必须经过 Evidence → Validation → Governor
            │
            ├── RepositoryContract
            │       Repository 只能 append，不能 overwrite
            │
            └── EvolutionContract
                    任何演化必须有 ROI 评估
```

---

## 六、Fitness 评估

### 当前状态

所有模块**没有 Fitness**。

### 需要的评估

```
Binary Sense      评分：63     需要：第一次真实分析
Governor         评分：91     需要：开始评价自己
Repository       评分：84     需要：计算能力而非文件
Memory           评分：79     需要：Experience → Principle 蒸馏
Evolution        评分：72     需要：Fitness 系统
Contract         评分：85     需要：升级为文明法律
```

---

## 七、新模块禁止规则

**任何新模块必须先回答**：

1. 为什么不能放进已有模块？
2. 为什么必须独立？
3. 生命周期是什么？
4. 未来会不会删？

**回答不了，禁止创建**。

---

## 八、R2 Phase-2 目标

```
R2 Phase-1：Civilization Construction（文明建造）
        ↓
R2 Phase-2：Civilization Convergence（文明收敛）
        ↓
R2 Phase-3：Civilization Growth（文明生长）
```

**Phase-2 目标**：
- 不是新增 100 个模块
- 是让现有模块形成**自洽、可演化、边界清晰**的文明内核

---

## 九、行动清单

| 优先级 | 任务 | 状态 |
|--------|------|------|
| P0 | 画文明地图（大图已完成） | ✅ |
| P0 | 删除重复角色（Governor/Admission/Curator/Archivist 合并） | ⏳ |
| P1 | Runtime 与 Civilization 目录分离 | ⏳ |
| P1 | Binary Sense 第一次真实分析（DLL/EXE/APK/ELF） | ⏳ |
| P1 | Mengpo 升级（Sleep/Wake/Archive/Rebirth） | ⏳ |
| P2 | Contract 升级为文明法律 | ⏳ |
| P2 | Fitness 评估系统 | ⏳ |
| P2 | Memory Distiller（Experience → Pattern → Principle → Law） | ⏳ |
| P3 | Law 和 Paradigm 库 | ⏳ |

---

*地图版本：v0.1*
*更新日期：2026-06-29*
*负责人：ACE*
