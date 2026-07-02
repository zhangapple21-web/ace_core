# Runtime Optimization Pattern Matrix（跨系统通用裁决框架）

**任务编号**: TASK-RUNTIME-OPT-001
**版本**: v2.0（证据驱动版）
**目标**: 不是形成一份 Apple 考古报告，而是沉淀一套跨 Apple、Claude Code、Search-R1、OpenHands 等系统都成立的 **Pattern Matrix**。

---

## 一、裁决框架（可复用）

### 判定维度（共 5 个，每个 0-2 分）

| 维度 | 定义 | 评分标准 |
|------|------|---------|
| **D1: Platform Independence** | 是否依赖特定平台/硬件/语言 | 2=完全跨平台 / 1=部分依赖 / 0=强绑定 |
| **D2: Civilization Alignment** | 是否符合 ACE 文明的核心价值观（结构>模型、约束驱动、append-only、ROI 原则） | 2=核心价值 / 1=边缘价值 / 0=无关 |
| **D3: ACE Gap Fill** | ACE 是否已经具备此能力 | 2=完全缺失需补充 / 1=部分有需强化 / 0=已有或不需要 |
| **D4: Pattern Durability** | 模式的时间稳定性（未来 5-10 年是否仍然成立） | 2=永恒成立 / 1=阶段性成立 / 0=很快过时 |
| **D5: Implementation Decoupling** | 模式是否与具体实现解耦（是否可以被多种方式实现） | 2=完全解耦 / 1=部分解耦 / 0=绑定特定实现 |

### 裁决规则

```
总分 = D1 + D2 + D3 + D4 + D5（最高 10 分）

Accept Threshold:
  总分 ≥ 7 → Accept（进入 Civilization）
  总分 5-6 → Partial Accept（进入 Runtime 或 Protocol，但不进入核心 Civilization）
  总分 < 5 → Reject（不吸收）

强制 Reject 条件（任一满足即 Reject，不看总分）:
  D1 = 0（强绑定特定平台）
  D4 = 0（很快过时）
  模式名称包含特定产品名（如 "Siri Integration"、"Spotlight API"）
```

---

## 二、Pattern Matrix（Apple 来源）

### 全量模式清单（来自 Apple Runtime Optimization 材料）

| # | Pattern 名称 | D1 | D2 | D3 | D4 | D5 | 总分 | 裁决 |
|---|-------------|----|----|----|----|----|----|------|
| 1 | Incremental First（增量优先） | 2 | 2 | 1 | 2 | 2 | **9** | ✅ Accept |
| 2 | Evidence Fingerprint Protocol（证据指纹协议） | 2 | 2 | 2 | 2 | 2 | **10** | ✅ Accept |
| 3 | Search Budget Policy（搜索预算策略） | 2 | 2 | 2 | 2 | 1 | **9** | ✅ Accept |
| 4 | Multi-Level Cache（多级缓存） | 2 | 1 | 1 | 2 | 2 | **6** | ⚠️ Partial |
| 5 | Capability Router（能力路由） | 2 | 1 | 1 | 1 | 2 | **5** | ⚠️ Partial |
| 6 | CoreML Acceleration | 0 | 0 | 0 | 0 | 0 | **0** | ❌ Reject |
| 7 | Neural Engine Hardware Acceleration | 0 | 0 | 0 | 0 | 0 | **0** | ❌ Reject |
| 8 | Swift Language Optimization | 0 | 0 | 0 | 1 | 0 | **1** | ❌ Reject |
| 9 | Spotlight Integration | 0 | 0 | 0 | 1 | 0 | **1** | ❌ Reject |
| 10 | Siri Shortcut Integration | 0 | 0 | 0 | 1 | 0 | **1** | ❌ Reject |
| 11 | Background Tasks API | 1 | 0 | 0 | 1 | 1 | **3** | ❌ Reject |
| 12 | URLSession Cache | 2 | 0 | 1 | 2 | 0 | **5** | ⚠️ Partial |
| 13 | NIO Routing Framework | 0 | 0 | 0 | 1 | 0 | **1** | ❌ Reject |
| 14 | Model Precision Compression（16位） | 1 | 0 | 0 | 1 | 1 | **3** | ❌ Reject |
| 15 | ETag / Last-Modified HTTP Protocol | 2 | 1 | 1 | 2 | 2 | **6** | ⚠️ Partial |

---

## 三、Accept 的证据论证（逐个）

### Pattern #1: Incremental First

```
Pattern: Incremental First（增量优先）

定义：
  文明的演化是 append-only 的，不是重建式的。
  只处理变化，不每次从零开始。

评分证据：
  D1 = 2: 跨平台证明
    - Apple 用 ETag/Last-Modified 实现
    - GitHub 用 commit hash 实现
    - 文件系统用 mtime 实现
    - 任何有"状态"的系统都可以增量
    → 不依赖任何特定平台

  D2 = 2: 文明价值证明
    - 符合 ACE 的 append-only 原则（经验沉积、概念生长）
    - 符合 ROI 原则（把资源用在新东西上）
    - 符合"文明是沉积的，不是重建的"哲学
    → 核心价值观

  D3 = 1: ACE Gap 证明
    - ACE 现状：FileScanner/RepoDiffScanner/FragmentIndex 已增量
    - 但 LocalArchaeologist/WebScout/ConceptMiner 还在部分全量
    - 还没有上升为全局原则
    → 部分缺失，需强化为全局原则

  D4 = 2: 时间稳定性证明
    - 增量思想在数据库领域存在 40+ 年（transaction log）
    - 在版本控制领域存在 30+ 年（diff/patch）
    - 未来 10 年不会消失，只会更普及
    → 永恒成立

  D5 = 2: 实现解耦证明
    - 可以用 ETag 实现（HTTP）
    - 可以用 hash 实现（文件）
    - 可以用 mtime 实现（文件系统）
    - 可以用 commit hash 实现（Git）
    - 可以用时间戳实现（通用）
    → 完全解耦，无数种实现方式

裁决：✅ Accept（总分 9 ≥ 7）
进入层：Runtime Pattern → Governance Principle
```

---

### Pattern #2: Evidence Fingerprint Protocol

```
Pattern: Evidence Fingerprint Protocol（证据指纹协议）

定义：
  任何证据都应有唯一指纹（hash/ETag/fingerprint），
  用于去重、溯源、增量更新、冲突检测。

评分证据：
  D1 = 2: 跨平台证明
    - HTTP 标准中有 ETag
    - Git 用 SHA-1/SHA-256
    - 文件系统用 MD5/SHA
    - 数据库用 primary key + hash
    → 任何有存储的系统都可以用

  D2 = 2: 文明价值证明
    - 符合 ACE 的证据管理需求（三重交叉验证需要证据溯源）
    - 符合血缘系统（Lineage）的追踪需求
    - 符合记忆系统的去重需求
    → 核心基础设施

  D3 = 2: ACE Gap 证明
    - ACE 现状：Task 有去重（task_id），但没有统一的证据指纹
    - 词库去重靠名字，不是内容指纹
    - 文件去重靠 hash，但不是统一协议
    - GitHub 去重靠 commit，但没有标准化
    → 完全缺失，必须建立

  D4 = 2: 时间稳定性证明
    - hash/fingerprint 概念存在 50+ 年
    - ETag 是 HTTP 标准（RFC 7232，2014年标准化）
    - 未来不会消失，只会更标准化
    → 永恒成立

  D5 = 2: 实现解耦证明
    - 可以用 MD5/SHA-1/SHA-256（任意 hash 算法）
    - 可以用 ETag（HTTP 标准）
    - 可以用 UUID（通用标识）
    - 可以用时间戳 + 内容组合
    → 完全解耦

裁决：✅ Accept（总分 10 ≥ 7）
进入层：Protocol / Evidence Management（核心基础设施）
```

---

### Pattern #3: Search Budget Policy

```
Pattern: Search Budget Policy（搜索预算策略）

定义：
  任何搜索/研究行为都应有预算上限，
  用于控制 ROI，防止无限深挖。

评分证据：
  D1 = 2: 跨平台证明
    - Search-R1 用 max_turns
    - 学术研究用 funding/time limit
    - 工业搜索用 API rate limit
    - 任何有限资源的系统都需要预算控制
    → 通用原则

  D2 = 2: 文明价值证明
    - 符合 ACE 的 ROI 原则（值不值得）
    - 符合 ACE 的资源有限约束
    - 符合 ACE 的收敛原则（不是无限扩张）
    → 核心治理原则

  D3 = 2: ACE Gap 证明
    - ACE 现状：完全没有显式预算控制
    - Researcher → Validator → Governor 一轮就完
    - 没有"证据不够就再来一轮"的循环
    - 没有"连续无提升就放弃"的判定
    → 完全缺失，必须建立

  D4 = 2: 时间稳定性证明
    - 预算控制是经济学/管理学的基本概念
    - 存在时间：永远
    → 永恒成立

  D5 = 1: 实现解耦证明
    - 可以用轮次上限实现（简单）
    - 可以用时间预算实现（通用）
    - 可以用置信度阈值实现（复杂）
    - 但具体实现方式有一定约束（需要计算置信度）
    → 部分解耦

裁决：✅ Accept（总分 9 ≥ 7）
进入层：Governance / Decision Protocol
```

---

## 四、Partial Accept 的证据论证

### Pattern #4: Multi-Level Cache

```
Pattern: Multi-Level Cache（多级缓存）

评分：
  D1=2, D2=1, D3=1, D4=2, D5=2 → 总分 6

Partial Accept 理由：
  - D2=1: 缓存是性能优化，不是文明核心价值
  - D3=1: ACE 已有 ProtocolLRUCache，只是零散，需要系统化但不是缺失
  → 不进入核心 Civilization，进入 Runtime 层

可复用判定标准：
  - D2=1 且 D3=1 的模式 → Partial Accept，进入 Runtime/Protocol
  - 不进入核心 Civilization，因为"只是更好，不是缺失"
```

---

### Pattern #5: Capability Router

```
Pattern: Capability Router（能力路由）

评分：
  D1=2, D2=1, D3=1, D4=1, D5=2 → 总分 5

Partial Accept 理由：
  - D2=1: 能力路由是治理的延伸，不是核心价值观
  - D3=1: ACE 已有 ObservationToTask，能力路由只是更精细版本
  - D4=1: 能力路由的实现方式可能随 AI 发展变化（未来可能有自动能力发现）
  → 不进入核心 Civilization，进入 Governance 延伸

可复用判定标准：
  - D4=1 的模式 → 时间稳定性存疑，需谨慎
  - 总分 5-6 且 D2=1 → Partial Accept，不进入核心
```

---

### Pattern #12: URLSession Cache / #15: ETag Protocol

```
Pattern: URLSession Cache
评分：D1=2, D2=0, D3=1, D4=2, D5=0 → 总分 5
Partial Accept 理由：D5=0（绑定特定实现），但本身是标准 HTTP 缓存
→ 只吸收"HTTP 缓存"概念，不吸收 URLSession 实现

Pattern: ETag / Last-Modified
评分：D1=2, D2=1, D3=1, D4=2, D5=2 → 总分 6
Partial Accept 理由：D2=1（文明价值边缘）
→ 已被 Evidence Fingerprint Protocol 包含，不需要单独进入
```

---

## 五、Reject 的证据论证（逐类）

### R1: Platform-Bound（D1 = 0）

```
强制 Reject 条件：D1 = 0（强绑定特定平台）

Pattern List:
  #6  CoreML Acceleration        → D1=0（绑定 Apple 硬件）
  #7  Neural Engine              → D1=0（绑定 M系列芯片）
  #8  Swift Language             → D1=0（绑定特定语言）
  #9  Spotlight Integration      → D1=0（绑定 macOS/iOS）
  #10 Siri Shortcut              → D1=0（绑定 Apple 产品）
  #13 NIO Routing Framework      → D1=0（绑定 Swift/NIO）

Reject 证据：
  - ACE 运行在 Windows/Linux/Mac 多平台
  - 绑定特定平台 = 换平台就失效
  - 不符合"跨系统通用 Pattern Matrix"的目标
  → 永久 Reject

可复用判定标准：
  D1 = 0 → 强制 Reject，不看总分
```

---

### R2: Low Civilization Value（D2 = 0 或 D2 + D3 ≤ 1）

```
Reject 条件：D2 = 0（无关文明价值）或 D2 + D3 ≤ 1

Pattern List:
  #6  CoreML Acceleration    → D2=0, D3=0 → Reject
  #7  Neural Engine          → D2=0, D3=0 → Reject
  #8  Swift Language         → D2=0, D3=0 → Reject
  #9  Spotlight Integration  → D2=0, D3=0 → Reject
  #10 Siri Shortcut          → D2=0, D3=0 → Reject
  #11 Background Tasks API   → D2=0, D3=0 → Reject
  #14 Model Precision        → D2=0, D3=0 → Reject

Reject 证据：
  - 这些是"怎么更快执行"，不是"ACE 是什么"
  - 没有这些，ACE 依然文明
  → 无关文明，Reject

可复用判定标准：
  D2 = 0 → 无关文明价值，Reject
  D2 + D3 ≤ 1 → 对 ACE 无实质帮助，Reject
```

---

### R3: Low Durability（D4 = 0 或 D4 = 1）

```
Reject 条件：D4 = 0（很快过时）

Pattern List:
  #6-#10 → D4=0-1（绑定当前硬件/API，会过时）
  #14 Model Precision → D4=1（量化方法会变化）
  #5 Capability Router → D4=1（能力发现方式可能变化）

Reject 证据：
  - D4=0: Neural Engine/Swift 会随 Apple 战略变化消失
  - D4=1: 需谨慎观察，不急着进入文明
  → 不值得沉淀为长期资产

可复用判定标准：
  D4 = 0 → 强制 Reject（很快过时）
  D4 = 1 → Partial Accept 或观察（阶段性成立）
```

---

### R4: Implementation-Bound（D5 = 0）

```
Reject 条件：D5 = 0（绑定特定实现方式）

Pattern List:
  #8  Swift Language     → D5=0（只能用 Swift 实现）
  #9  Spotlight          → D5=0（只能用 Spotlight API）
  #10 Siri Shortcut      → D5=0（只能用 Siri API）
  #13 NIO Framework      → D5=0（只能用 NIO）
  #12 URLSession Cache   → D5=0（绑定 URLSession，但概念可吸收）

Reject 证据：
  - D5=0 意味着"只有一个实现方式"
  - ACE 不绑定特定实现，只用概念
  → Reject 实现，只吸收概念（如果 D1-D4 足够高）

可复用判定标准：
  D5 = 0 且 概念有价值 → 吸收概念，Reject 实现
  D5 = 0 且 概念无价值 → 完全 Reject
```

---

## 六、跨系统 Pattern Matrix（可扩展）

此 Matrix 可用于其他系统的考古：

### Claude Code（待考古）

| Pattern | D1 | D2 | D3 | D4 | D5 | 总分 | 裁决 |
|---------|----|----|----|----|----|----|------|
| Tool Calling Loop | ? | ? | ? | ? | ? | ? | 待评估 |
| Token Budget Control | ? | ? | ? | ? | ? | ? | 待评估 |
| Context Compression | ? | ? | ? | ? | ? | ? | 待评估 |
| Sandbox Isolation | ? | ? | ? | ? | ? | ? | 待评估 |

### Search-R1（已考古）

| Pattern | D1 | D2 | D3 | D4 | D5 | 总分 | 裁决 |
|---------|----|----|----|----|----|----|------|
| Interleaved Search Loop | 2 | 2 | 2 | 2 | 2 | **10** | ✅ Accept |
| Evidence Pool | 2 | 1 | 1 | 2 | 2 | **6** | ⚠️ Partial |
| Search Budget (max_turns) | 2 | 2 | 2 | 2 | 1 | **9** | ✅ Accept |

### OpenHands（待考古）

| Pattern | D1 | D2 | D3 | D4 | D5 | 总分 | 裁决 |
|---------|----|----|----|----|----|----|------|
| Action-Observation Loop | ? | ? | ? | ? | ? | ? | 待评估 |
| Environment Sandbox | ? | ? | ? | ? | ? | ? | 待评估 |
| History Management | ? | ? | ? | ? | ? | ? | 待评估 |

---

## 七、最终裁决（Governor 签署）

### Accept 进入 Civilization：3 个

| Pattern | 总分 | 进入层 | 证据编号 |
|---------|------|--------|---------|
| Incremental First | 9 | Governance Principle | 见 §III.1 |
| Evidence Fingerprint Protocol | 10 | Protocol / Evidence | 见 §III.2 |
| Search Budget Policy | 9 | Governance / Decision | 见 §III.3 |

### Partial Accept 进入 Runtime/Protocol：3 个

| Pattern | 总分 | 进入层 | 理由 |
|---------|------|--------|------|
| Multi-Level Cache | 6 | Runtime | 只是性能优化，非核心 |
| Capability Router | 5 | Governance 延伸 | 是 ObservationToTask 延伸 |
| ETag Protocol | 6 | Protocol | 已被 Evidence Fingerprint 包含 |

### Reject（不可进入 ACE）：9 个

| Pattern | Reject 原因 | 证据编号 |
|---------|------------|---------|
| CoreML | R1(D1=0) + R2(D2=0) | 见 §V.R1 |
| Neural Engine | R1(D1=0) + R2(D2=0) | 见 §V.R1 |
| Swift | R1(D1=0) + R4(D5=0) | 见 §V.R1 |
| Spotlight | R1(D1=0) + R4(D5=0) | 见 §V.R1 |
| Siri | R1(D1=0) + R4(D5=0) | 见 §V.R1 |
| Background Tasks | R2(D2=0) + D3=0 | 见 §V.R2 |
| NIO Framework | R1(D1=0) + R4(D5=0) | 见 §V.R1 |
| Model Precision | R2(D2=0) + R3(D4=1) | 见 §V.R2 |
| URLSession | R4(D5=0)（概念已吸收） | 见 §V.R4 |

---

## 八、可复用判定标准总结

此框架可用于任何系统的 Runtime Pattern 考古：

```
┌─────────────────────────────────────────────────────┐
│         Pattern Accept/Reject 判定标准              │
├─────────────────────────────────────────────────────┤
│                                                     │
│  Accept（进入 Civilization）                        │
│    - 总分 ≥ 7                                       │
│    - D1 ≥ 1（至少部分跨平台）                       │
│    - D2 ≥ 1（至少边缘文明价值）                     │
│    - D4 ≥ 1（至少阶段性稳定）                       │
│                                                     │
│  Partial Accept（进入 Runtime/Protocol）           │
│    - 总分 5-6                                       │
│    - 不满足 Accept 全部条件                        │
│    - 但有足够价值值得吸收                          │
│                                                     │
│  Reject                                            │
│    - 总分 < 5                                       │
│    - 或 D1 = 0（强制 Reject）                      │
│    - 或 D2 + D3 ≤ 1（强制 Reject）                 │
│    - 或 D4 = 0（强制 Reject）                      │
│    - 或 D5 = 0 且概念无价值（Reject 实现+概念）    │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

**Governor 签署**：此 Pattern Matrix 是 ACE Civilization 的可继承资产，可用于后续所有 Runtime Optimization 考古任务。