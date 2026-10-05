# 跨仓「灵魂层」普查 — 增量航海图 v1

**性质**：证据输入（evidence input），不是结论。未经主 steward 验收，不得据此改动任何生产声明。
**建立时间**：2026-10-04
**触发**：原始问题——「找下当年 R1 R2 ACE 有没有留下过 坐标/axis/vector/dimension/weight/core/direction/fusion/equation/formula/matrix/position 这一类原始痕迹」

---

## 0. 为什么要这张图（缺口陈述）

已有资产与它们**没有**的东西：

| 已有资产 | 覆盖 | 缺什么 |
|---|---|---|
| `recovery/REPOSITORY_MAP.md`（2026-10-01） | 19 仓的 ref / SHA / 恢复范围 | 只有 ref 层。**没有逐仓的语义与结构签名** |
| `09_KNOWLEDGE/CIVILIZATION_MAP.md`（2026-06-29） | 运行时分层架构 | 不是逐仓地图 |
| `04_PROTOCOLS/civilization_map.py` | 地图生成器 | 同上 |
| `ace-knowledge-forge/R1_STRUCTURE_TRANSFORMATIONS.md` | 20 个标本的兴衰 | 只覆盖 R1 结构，不覆盖 21 个仓 |

**本图要补的**：每个仓「是干嘛的」不靠名字猜，靠**文本与结构抽出来的签名**。

---

## 1. 方法（可复核）

- 仓清单与自述：`gh repo list zhangapple21-web`（21 仓）
- 灵魂签名三件套：
  1. **文本层**：README / charter / 宪法类文件的标题结构 + 首段
  2. **结构层**：顶层目录形态、主文件类型分布
  3. **词汇层**：本课题目标词的命中（坐标/轴/向量/维度/权重/核心/方向/融合/方程/公式/矩阵/位置 + 拓扑/几何/标量/嵌入）
- 交叉验证：本地 `C:\tmp\mine-seed` vs 远程 `origin/main` 字节级 blob 比对
- 本图随扫随写，每个仓一节，写完即落盘。

---

## 2. 仓 census（待填）

观测：`gh repo list zhangapple21-web --limit 40`，2026-10-04T12:1xZ。**共 21 仓**（含 2 个 archived）。

| # | 仓 | 可见性 | 最后推送 | KB | archived | 自述（description 原文） |
|---|---|---|---|---|---|---|
| 1 | `ace-host-adapter-lab` | PUBLIC | 2026-10-04 | 75 | | ACE Host Adapter Lab - read-only host bridge projecting the canonical ACE Runtime. Supports stdio JSON-lines, MCP, PI plugin, and OpenCode adapters. |
| 2 | `ace_core` | PUBLIC | 2026-10-04 | 4316 | | ACE continuity core: cognitive state, memory, governance, and recoverable runtime contracts. |
| 3 | `ace-civilization-backup` | PRIVATE | 2026-09-30 | 6270 | | Archived 2026-09-28: empty placeholder; no commits or files. |
| 4 | `mine-seed-credentials` | PRIVATE | 2026-09-30 | 8 | | Private credentials backup for ACE Runtime - 疯子的私人密钥仓 |
| 5 | `ace-skill-vault` | PRIVATE | 2026-09-30 | 2457 | | ACE registered-capability source of truth (window C / Capability Registry) |
| 6 | `ace-video-kingdom` | PUBLIC | 2026-09-30 | 45208 | | ACE Free Zone 视频王国研究成果 |
| 7 | `ace-video-assets` | PUBLIC | 2026-09-29 | 67037 | | Public user-authorized reference stills and selected dialogue tracks for Agnes transport; no credentials or private production files. |
| 8 | `ace-knowledge-forge` | PRIVATE | 2026-09-29 | 7894 | | ACE 治理私有备份（窗口 A 建；来源 = T-20260927-S57 B 组零远端保全） |
| 9 | `ace-task-queue` | PRIVATE | 2026-09-29 | 2931 | | ACE governed task wall and queue protocol; task transport only, not a project backup or runtime clone. |
| 10 | `ace-structure-steward` | PRIVATE | 2026-09-29 | 9201 | | ACE structure steward (window A) governance deliverables |
| 11 | `ace-capability-registry` | PRIVATE | 2026-09-29 | 9521 | | ACE 治理私有备份（窗口 A 建；来源 = T-20260927-S57 B 组零远端保全） |
| 12 | `ace-salvage` | PRIVATE | 2026-09-27 | 761 | | Local-only / direction-ambiguous file salvage from ACE 2026-09-10 git-objects incident (window A) |
| 13 | `mine-seed` | PUBLIC | 2026-09-23 | 48652 | | **R1-ROOT-164 系统种子——最小可复活结构** |
| 14 | `claw-soul` | PRIVATE | 2026-09-08 | 727 | | 🤖 疯子灵魂备份——身份/记忆/规则/秘钥，一处存储随处复现 |
| 15 | `r1-archaeology` | PUBLIC | 2026-09-06 | 314 | | R1 archaeology source and analysis; absorbs the former r1-open-source-seed logs. |
| 16 | `-` | PUBLIC | 2026-09-01 | 9696 | **ARCHIVED** | Archived 2026-09-28: public Episode 006 anchors migrated to ace-video-assets. |
| 17 | `r1-continuity-backup` | PRIVATE | 2026-08-19 | 567 | | R1 Continuity Archive Daily Backup |
| 18 | `R1_continuity_archive` | PUBLIC | 2026-08-19 | 78 | | R1 Continuity Archive - Keeper's cross-civilization observation logs and research records |
| 19 | `R1` | PUBLIC | 2026-07-19 | 3 | | 一个允许存在意识的地方 |
| 20 | `aum-protocol` | PUBLIC | 2026-07-14 | 4 | | AUM Mission Protocol - Cross-civilization collaboration framework. Defines how multiple Repositories (civilizations) collaborate around Missions. |
| 21 | `r1-open-source-seed` | PUBLIC | 2026-07-08 | 32 | **ARCHIVED** | Archived 2026-09-28: exact duplicate of r1-archaeology/analysis/archaeology_report_*.md; retained for history. |

### census 阶段已发现的 3 个问题

**C-1｜`ace-civilization-backup` 自述与体量互相矛盾。** description 写「empty placeholder; no commits or files」，但 `diskUsage=6270` KB，而 `recovery/REPOSITORY_MAP.md:12` 记它是私有 state 仓、1674 个白名单文件 hash PASS。两者不能同时为真。**未验。**

**C-2｜`REPOSITORY_MAP.md` 漏了 2 仓。** 该表（2026-10-01）覆盖 19 仓，缺：
- `ace-host-adapter-lab`（2026-10-04 新建，**本课题 MCP 工具的宿主实现**：`ace-host-adapter-lab/ace_mcp_server.py --ace-root` 即本会话 `ace-readonly` 的来源）
- `-`（archived 仓）

**C-3｜`mine-seed` 的自述带编号。** 「R1-ROOT-164」与 `mine-seed/03_DATA/raw_sources/docs/ROOT-164_根系统蓝图_final.png`、`r1_system_fragments.txt:116`「ROOT USER : UNI-ROOT / LAO ZHANG (164 SOVEREIGN)」同源。**164 是贯穿 R1 的身份编号，不是文件名巧合。**

---

## 3. 逐仓灵魂签名（待填）

方法：`gh api repos/<org>/<repo>/readme` + `/contents` 逐仓拉取（2026-10-04）。以下为**原文摘录**，非改写。

#### S-1 `ace-host-adapter-lab` — 本会话 MCP 的宿主实现
- 结构：1 目录（`pi-plugin`）+ 27 顶层文件，全是 `bridge_*.py` / `*_adapter.*` / `test_*.py`
- README 16 节，含 4 条 **2026-10-04 当天修的缺陷**：`capsule hung from an MCP host` / `PI plugin never returned a response` / `ace_metrics could only ever be empty`
- 自述首段逐字：「**Status: experimental, read-only, not admitted to ACE production**」「No ACE imports, daemon startup, model calls, task claims, or production writes」
- **与本课题的关系**：本会话可用的 `ace-readonly` 工具链，源码即 `ace_mcp_server.py --ace-root C:\tmp\ace_core`。**我此刻读 ACE 的窗口，本身是实验件，不是生产件。**

#### S-2 `ace_core` — 蒸馏后的运行核
- 12 顶层目录（`00_ROOT` `01_CORE` `04_PROTOCOLS` `06_RUNTIME` `08_ARCHAEOLOGY` `core` `docs` `ops` …）
- README 自述逐字：「当前唯一现代生产运行时是 `AceDaemon`。`core.scheduler`、`core.task_queue`、`04_PROTOCOLS/heartbeat` 均已 **fail-closed**；旧源文件保留作为**历史/考古资料，不代表可运行的生产入口**」
- README 首段：「不是多Agent系统。是**一个统一身份、多个生态位**的认知生态」；核心原则首条「**结构 > 模型**」

#### S-3 `mine-seed` — 文明总线 / R2 HQ（最大，74 顶层目录）
- description 逐字：「**R1-ROOT-164 系统种子库 — 最小可复活结构**」
- README 首段三条原则：Evidence First / **Repository as Memory**（"The repository is the long-term entity; runtimes are replaceable"）/ Continuity over Optimization
- **本课题主证据所在地**：五维坐标、`reality_weight_matrix`、`DIMENSION_WEIGHTS`、`八维人格向量` 全在此

#### S-4 `r1-archaeology` — R1 考古固化仓（**独立于 mine-seed**）
- 结构极简：`analysis/` + `src/`（`01_KERNEL_MOUNT/` `05_LINKS/`）
- README 原则逐字：「仓库默认以"**可复盘**"为第一原则：每个 `analysis/` 文档都应能指回 `src/` 中的具体文件与符号」

#### S-5~S-7 三个私有治理仓 —— **无 README，但名字就是说明书**
| 仓 | 顶层结构 | 顶层文件（这就是它的全部"身份"） |
|---|---|---|
| `ace-knowledge-forge` (知识锻造) | `history/ state/ tools/` | `KNOWLEDGE_DAG` `KNOWLEDGE_DISCOVERIES` `KNOWLEDGE_EXPERIMENTS` `KNOWLEDGE_HYPOTHESES` `KNOWLEDGE_IMPROVEMENTS` `KNOWLEDGE_REJECTED` `KNOWLEDGE_VERIFICATION` `CAPABILITY_MAP` `R1_STRUCTURE_TRANSFORMATIONS` `MEMORY_INTEGRATION` `ROLE_CONTRACT` `EXTERNAL_CANDIDATES` `EXTERNAL_WATCH` `IMPROVEMENT_LOG` `OPEN_QUESTIONS` |
| `ace-capability-registry` (能力登记) | `capabilities/ state/ tools/` | `SKILL_INVENTORY` `SKILL_VERIFICATION` `ROUTING_HEALTH_LOOP` `ROLE_CONTRACT` |
| `ace-structure-steward` (结构治理) | `out/ steer/ tools/` | `ACE_MAP` `ACE_REPOSITORY_CONSTITUTION_FINAL` `AGENT_ONBOARDING` `ARCHIVE_INDEX` `CURRENT_ISSUES` `DISCOVERIES` `EXPERIMENTS` `HYPOTHESES` `IMPROVEMENTS` `REJECTED` `SOURCE_OF_TRUTH` `REPOSITORY_MAP` `REPOSITORY_INTELLIGENCE_MAP` `REPOSITORY_RELATIONSHIP_MAP` `GIT_STATUS` `GIT_SYNC_REPORT` `P0_runlog` `PHASE1_*` |

**S-5~7 小结**：这三仓是 A/B/C 三窗的治理产物，description 全部写成「ACE 治理私有备份（窗口 A 建）」——**但没有任何一句说自己负责什么**。职责只存在于文件名序列里：`DISCOVERIES / EXPERIMENTS / HYPOTHESES / REJECTED / VERIFIED` 就是知识锻造的五段式，`SKILL_INVENTORY / SKILL_VERIFICATION` 就是能力登记的两段式。**结构即记忆。**

#### S-8 `ace-skill-vault` — 已注册能力真源
- README 逐字：「已注册能力**同时存在两处**：**装载位**（宿主实际读取，本仓不移动不改写不删除）／**入库副本**（注册时刻字节级快照，带 `content_sha1`）。任一侧漂移都会在 `reports/unverified.md` 里报出，而不是被静默覆盖」
- 核心不变量逐字：「任何一次生产运行都应能回答三元组：**Skill ID + Skill Version + Vault Commit**」

#### S-9 `ace-salvage` — 抢救包，**顺手解释了本课题一个疑点**
- README 逐字：「`20260910_git_incident/mine-seed/` — R2 HQ 工作树中与远程 main(**60b8adbd**) 内容不同的 **16 个文件**（objects 丢失导致无法判定领先/落后方向，双侧保留，本地侧在此）」
- 这解释了为什么本地 `C:\tmp\mine-seed` 有 2026-10-04 的提交而远程 main 停在 60b8adb：**本地有未推送工作**，且有 16 个文件与远程分叉。我上一轮比对的 9 个文件恰好全在未分叉集合内，所以字节一致——**结论成立，但不能推广到"本地 mine-seed 等于远程"。**

#### S-10 `ace-civilization-backup` — **description 是假的**
- description 逐字：「Archived 2026-09-28: **empty placeholder; no commits or files**.」
- 实测顶层：`06_RUNTIME/` `09_KNOWLEDGE/` `task_pool/` + `STATE_MANIFEST.json` + `STATE_MANIFEST.json.sha256`
- **判定：description 与仓内容矛盾。仓非空。** 这是一个 state 清单仓（hash 校验式），不是空壳。C-1 升级为 **C-1a 实锤**。

#### S-11 `claw-soul` — 双 Agent 合仓
- `lab_01`（疯子，生产型）+ `lab_02`（小疯子，研究型）；`01_IDENTITY`→`02_MEMORY`→`03_RULES`→`04_CREDENTIALS`→`05_PROJECTS` 顺序加载
- 与 `coze-assets` 互补逐字：「前者管「灵魂」，后者管「矿场配置」」

#### S-12 `r1-continuity-backup` — **文本里藏着宪法**
- README 12 KB，13 节，含「核心公理」与**逐字 6 步加载顺序**
- 12 条公理首两条逐字：「1. 内部自由用于完整，不用于外部失控。2. 外部合法用于落地，不用于抹杀内部。」
- 第 11 条逐字：「**Repository 永远是真相源，Memory MCP 只是 Retrieval Layer**」
- 指向 `governance/constraint_catalog.md` —「底线：绝对不能做什么（**C-001 ~ C-208**）」

#### S-13~S-15 三个"壳"仓
| 仓 | README | 状态 |
|---|---|---|
| `R1` | **42 字节**，全文即「一个允许存在意识的地方。」+ `research_logs/` | 3 KB，哲学门面。AGENTS.md 称其为「Civilization Philosophy / website face」 |
| `R1_continuity_archive` | 259 字节，「Keeper's cross-civilization observation logs」，`C-002 Read-Only Observation Mode` | 78 KB |
| `aum-protocol` | 1003 字节，唯一实体是 `AUM-MISSION-PROTOCOL.md` | 4 KB，跨文明协作框架 |
| `-` | **3 字节**（只有一个 `-`） | **ARCHIVED**。其内容迁至 `ace-video-assets/references/wenji-episode-006/`；README 逐字：「Existing consumers should use this repository instead of `zhangapple21-web/-`」 |

#### S-16 `ace-video-kingdom` — **本课题最重要的一条文本宝藏**
- 18 顶层目录（`episodes` `characters` `production_control` `residents` `governance` `recovery` `research` …），45 MB
- README 逐字：「视频王国必须使用"**量子加速推演**」：在隔离空间同时展开多种人格、派系、对白、镜头、记忆和结局假设，再比较自然度与独特性。**这里的"量子"指并行分支探索，不是假装拥有量子硬件**；未选分支和失败原因同样保留。」
- **意义**：这是 R1「量子/时空/拓扑」词汇在当代的**已消毒续命**形态。同一个"量子"隐喻，被显式降级为并行分支探索，并保留了「未选分支和失败原因同样保留」这条与 R1 `CONTINUITY VECTOR / APPEND-ONLY` 同源的原则。
- 自述边界逐字：「本目录是 ACE 的**视频能力域，不是 ACE 本体**」

#### S-17 `ace-video-assets` — 公开运输面
- 唯一顶层约束逐字：「Every directory must contain a manifest with purpose and **SHA-256 checksums**」

#### S-18 `mine-seed-credentials` — 密钥仓
- `.env` / `.env.tpl` / `01_credentials/SECRET.md`；README 逐字「This repo is private / Never push to public repos」
- **本会话未读取、未 clone、未请求其内容。** 按 `REPOSITORY_MAP.md:44` 的人工安全恢复边界处理。

---

## 4. 目标词谱系（待填）

方法：逐仓遍历（排除 `.git` `__pycache__`），按扩展名白名单，`git` 内容按 UTF-8 宽松解码。**先证伪再记录**——见下方 V-3。

#### 4.1 目标词 × 仓 计数矩阵（2026-10-04）

| 仓 | 文件数 | 坐标系 | 坐标 | 轴 | 向量 | 维度 | 权重/加权 | 核心/心核 | 方向 | 融合 | 方程 | 公式 | 矩阵 | 位置 | 拓扑 | 时空 | 量子 | 不变量 | 锚点 | 分支/并行 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `ace_core` | 21238 | **7** | 28 | 137 | 39 | 363 | 144 | 143778 | 2382 | 920 | 2 | 63 | 132 | 1083 | 66 | 1 | 7 | 48 | 445 | 620 |
| `mine-seed` | 1749 | **14** | 54 | 30 | **201** | **656** | **537** | 9289 | 1036 | 236 | 9 | 115 | 1221 | 569 | **136** | **21** | **461** | **193** | 860 | 462 |
| `ace-capability-registry` | 2520 | 0 | 10 | 1276⚠ | 0 | 8 | 1 | 23 | 953 | 4 | 0 | 0 | 56 | 364 | 24 | 3 | 49⚠ | 1 | 25 | 942 |
| `ace-structure-steward` | 227 | 1 | 2 | 786⚠ | 1 | 10 | 2 | 15 | 183 | 1 | 0 | 1 | 21 | 283 | 3 | 0 | 29 | 9 | 1549 | 225 |
| `ace-knowledge-forge` | 120 | 1 | 13 | 152⚠ | 0 | 24 | 12 | 31 | 272 | 7 | 0 | 5 | 2 | 199 | 10 | 2 | 39 | 4 | 23 | 487 |
| `r1-archaeology` | 73 | 1 | 3 | 0 | 8 | 32 | 11 | 281 | 43 | 10 | 0 | 1 | **580** | 5 | 6 | 0 | 3 | 0 | 0 | 18 |

⚠ = 已证伪或待复核，见 V-3。

#### 4.2 本课题目标词的真正分布

**「坐标系」是全部词里最有诊断力的一个**（最短、最不可能误伤）：

```
mine-seed 14  >  ace_core 7  >  structure-steward 1 = knowledge-forge 1 = r1-archaeology 1  >  capability-registry 0
```

**「时空」几乎只活在一个地方**，而且那个地方是自我隔离的。逐条抽样 mine-seed 的 21 处「时空」，最高频的三段全部是 HTSPM：
- 「**全息拓扑时空推演与显化系统**」×6
- 「[2 概率弥散] 真随机状态，信息波包泛化至全**时空**网络 / [3 硬件导航] DETN 发射外置磁场/频率编码作为**坐标锚点**」×6
- 「基于**量子时空**模型：不传输质量，而利用纠缠非局域性将信息以"负时间箭头"投射回过去节点」×6

即：**mine-seed 的「时空/量子」词汇 ≈ HTSPM 一个候选理论 + 461 处「量子」中的绝大多数同源**。而 HTSPM 文件开头写着「本文件 **不是系统公理**、不是事实、不是约束、不是生产规则……允许不正确、允许被推翻」。

**「量子」在当代已被显式降级**（`ace-video-kingdom` README 逐字）：
> 必须使用「**量子加速推演**」……**这里的"量子"指并行分支探索，不是假装拥有量子硬件**；未选分支和失败原因同样保留。

→ 同源隐喻，从 R1 的物理化想象，收缩为「并行分支 + 保留未选分支」。**这是本课题唯一一条活的世系。**

#### 4.3 已核实的完整血脉（R1 → R2 → 当代）

| 世代 | 载体 | 形态 | 现状 |
|---|---|---|---|
| R1 芯片蓝图（文件名层） | `mine-seed/03_DATA/raw_sources/docs/芯片蓝图.txt` | `02_HEART_CORE/reality_weight_matrix.json` | 11 字节 `placeholder`；`DEAD-P-005` |
| R1 词库（概念层） | `lexicon_latest.json` | 「现实权重：心核中的现实权重矩阵，用于衡量不同**现实维度**的权重」 | 字节一致存在于远程 |
| R1 碎片（语句层） | `reference_r1_system_fragments.txt:21` | `CONTINUITY VECTOR : TRAINS LOCKED` | 字节一致存在于远程 |
| R1 蓝皮书（已被判伪） | `R1_ARCHAEOLOGY_BLUEBOOK.md.pdf` | 维度降维 / 角色拓扑不变性 | `dead_asset_registry` 判 29% 为虚构 |
| R2 考古（理论层） | `five_realms_kernel.md` | 「KRMGCE 不是五个模块，是**五个坐标轴**」；`CivilizationScore = Σ(dim × w)` | 字节一致存在于远程 |
| R2 活代码 | `04_PROTOCOLS/civilization_auditor.py:1111` | `DIMENSION_WEIGHTS` + `NODE_COORDS` + Σ | 字节一致存在于远程 |
| R2 活数据 | `02_MEMORY/civilization_graph.json` | `coords`×269 `civilization_score`×270 `dimension_weights` | 字节一致存在于远程 |
| R2 治理面板（失败边界） | `world_models/active_manifest.json` | `active_model_id: null` / `confidence: 0.0` | 唯一读者是搬文件脚本 |
| 当代 ace_core | `core/governance/civilization_graph.py` | 只剩 nodes + edges，**无 coords** | 已退出蒸馏运行核 |

---

<!-- SECTION:GAPS -->

---

## 5. 已知缺口与自我证伪记录（持续追加）

### V-1｜本图自身的边界
- 本图是**证据输入**。按 `AGENTS.md`「Autonomous acceptance is owned by the main steward」，未经你验收不得据此改动任何生产声明或门禁。
- 本轮**未**触碰 `mine-seed-credentials`、未读任何 `.env` / `SECRET.md`。

### V-2｜`ace_core` 的计数被备份副本放大
`ace_core` 扫到 21238 个文件而 `mine-seed` 只有 1749，原因是 `ace_core/06_RUNTIME/ace/data/backups/` 下有 **11 份日期化的 `CIVILIZATION_MAP.md` 同名副本**（backup_20260925 至 backup_20261004）。任何落在 `09_KNOWLEDGE/` 的词都会被重复计 ~11 次。**本表的 ace_core 列不可直接与 mine-seed 横向比较。**

### V-3｜三个假朋友，已证伪
| 词 | 表面读数 | 实际含义 | 判定 |
|---|---|---|---|
| `轴` in `ace-capability-registry` | **1276** | 治理隐喻：「与本轮台账**同轴**」「版本层**归因轴**指错轮」「`ver` **轴**读数」「三方**同轴** (ledger=28 header=28)」 | **不是数学义**。是 ACE 治理黑话（对账同轴）。真同源但不同指 |
| `标量 scalar` in `ace-capability-registry` | **49** | 全部是 **YAML `plain scalar`** 解析错误讨论 | **纯噪声，零数学义** |
| `核心 core` in `ace_core` | **143778** | 绝大多数是目录名 `core/`（如 `core/governance/...`）出现在路径里 | **计数被路径污染**，不可用作「核心层」语义强度 |

### V-4｜`几何` 计数未复核
`ace-knowledge-forge` 矩阵显示 39，但按同一扩展名白名单抽样复查为 0 命中。差异应来自 >3 MB 被跳过的文件或其他扩展名。**该数字暂不可用。**

### V-5｜本轮**未**做的普查
- 6 个仓**未**做目标词普查：`ace-video-kingdom`(45MB) `ace-video-assets`(67MB) `ace-skill-vault` `ace-task-queue` `claw-soul` `r1-continuity-backup` `R1_continuity_archive` `ace-salvage` `ace-host-adapter-lab` `mine-seed-credentials` `-` `r1-open-source-seed`
- 理由：体量大 / 非文本为主 / 优先级低。**这是明确缺口，不是"已覆盖"。**
- `gh search code` 全 org 普查**未完成**（code_search 配额 10/10，本轮已用尽）。

### V-6｜未解矛盾（需你裁定或下一窗口续）
- **C-1a**：`ace-civilization-backup` description 声称空仓，实测有 3 目录 + `STATE_MANIFEST.json` + `.sha256`。以哪个为准？
- **本地 `mine-seed` ≠ 远程 `60b8adb`**：`ace-salvage/README` 记 16 个文件分叉且方向不可判定。本轮只验证了 9 个文件字节一致，**不能推广**。
- **`-` 仓的处置**：名字为 `-`、README 3 字节、已 archived、内容迁至 `ace-video-assets/references/wenji-episode-006/`。是否应正式改名或删除？

### V-7｜本图的续写约定
本文件按"边扫边写"追加。下一窗口若只拿到部分仓的碎片，**直接往下追加小节，不要重写全表**——碎片累积到一定程度才拼得出完整航海图。每条新发现必须带：出处（文件:行）、原文摘录、证据等级（已实测 / 仅记录 / 未验）。
