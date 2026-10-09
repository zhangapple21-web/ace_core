# CLI 指令上下文决策 v1

状态：`ACTIVE` · 日期：2026-10-09 · 范围：`core/opencode_worker.py` 与
`core/miner_pool/providers/opencode_cli.py`

## 1. 起因

原始提议：每次调用 OpenCode CLI 前，把 ACE 正式 `AGENTS.md` 复制进本次调用的
临时工作目录，让每次 CLI 都有明确、可追溯的 ACE 指令上下文。

核验后**该前提不成立**，路线已改。本文记录核验证据、改动与仍然开放的问题。

## 2. 已核验事实

| 事实 | 证据 |
| --- | --- |
| `opencode run` 没有 `--dir`，全局 flag 也没有 | `opencode v2.0.6` `run --help` 输出 |
| 工作目录由 subprocess 的 `cwd` 决定 | `core/opencode_worker.py` `_run_command(command, cwd=...)` |
| V2 只认 `AGENTS.md`，不回落 `CLAUDE.md` | <https://opencode.ai/v2/docs/instructions/> |
| 加载顺序：全局文件 + 从工作目录向 home 方向逐级；工作区在 home 之外时停在 project root | 同上 |
| `--file` 只是把文件附加到单条消息，不进指令面 | 同上 + `run --help` |
| 交付链的工作目录**就是生产仓库根** | `ace_daemon.py:3931` `DeliveryExecutor(self.base_dir, ...)`，`base_dir = Path(__file__).parent` |
| 隔离临时目录只发生在 miner 聊天链 | `core/miner_pool/providers/opencode_cli.py` `tempfile.mkdtemp(prefix="ace_opencode_cli_")` |

**推论（重要）**：交付链的 cwd 已经是 `C:\tmp\ace_core`，那里的 `AGENTS.md`
本就落在 V2 的加载范围内。原提议所依据的"每次都新建独立临时目录"只适用于聊天
链——而聊天链恰恰是最不需要 20KB 运行手册的那条。把 staging 用到交付链上不仅
多余，还会去改写生产的 `AGENTS.md`。

## 3. 注入有效性实测

问模型一个只有读了指令文件才能回答的问题，全程不提文件、不用工具。
模型 `opencode/nemotron-3.5-lightning-free`，生产条件（无 `--auto`，共享后台服务）。

| 组 | 条件 | 答出口令 | 使用工具 | 耗时 |
| --- | --- | --- | --- | --- |
| A | staged `AGENTS.md` 含口令 | **是** | 否 | 3.2s |
| B | 无指令（对照） | 否 | 否 | 240s 超时 |
| C | staged 但内容无关 | 否 | 是（去找文件） | 42.6s |

结论：staging 的文件**确实作为指令进入上下文**，不是磁盘上的一个文件；B 排除了
nonce 从别处泄漏，C 排除了"有个 AGENTS.md 就听话"。

## 4. 数据边界实测

真实 `C:\tmp\ace_core\AGENTS.md`：20255 bytes / 449 行 / 约 4.8k tokens。
用 ACE 自己的 `validate_data_boundary(target="MODEL_CONTEXT")` 判定：

| 分级 | 结果 |
| --- | --- |
| `CORE` / `PRIVATE` | `sensitive_data_cannot_egress` |
| `CAPABILITY` / `STRUCTURE` | `trusted_sanitization_receipt_required` |
| `PUBLIC` | 通过 |

内容信号：含私有仓名 `coze-assets`、外部组织名、`Never wait for the user` 等
运行指令；**不含**凭据形状内容。

结论：该文件只有声明为 `PUBLIC` 才能出站，而它含私有仓名——声明 `PUBLIC` 是谎报
分级。在 sanitizer receipt 存在之前，"给交付链打开 staging"在 ACE 自己的门下
走不通。

## 4b. 非交互权限实测

| 能力 | 条件 | 结果 |
| --- | --- | --- |
| 读**工作目录之外**的文件 | 无 `--auto`，共享后台服务 | 被拒：`The user declined this tool call` |
| 写工作目录内的文件 | 无 `--auto`，共享后台服务 | 成功，13.4s，内容逐字节正确 |
| 写工作目录内的文件 | `--standalone` | 成功，9.5s，内容逐字节正确 |

`opencode run` 遇到 `ask` 会自行拒绝，而默认策略里唯一的 `ask` 来自
`external_directory`（<https://opencode.ai/v2/docs/permissions/>）。因此这个墙是
**跨目录读取**被拒，不是工具能力被封。交付链要写的是工作目录内的文件，不受影响；
需要读工作区外文件的调用才是受限的那一类。

## 5. 已落地的改动

**`core/opencode_worker.py`**（唯一调用面，provider 与 daemon 交付都走这里）

1. `INSTRUCTION_MODES = ("off", "workspace")`，**默认 `off`**。原提议的"缺 MD
   即拒绝调用"改为只在显式开启时生效——避免仓库里某个文件不见了就把免费层整体
   打死，符合连续性公理"先保可运行"。
2. `_stage_instruction()`：按字节复制、**hash 算源文件**、写入后读回校验；发生在
   预运行指纹**之前**，所以这个文件不会被算成模型干的活。
3. 自覆盖保护：源文件与工作区 `AGENTS.md` 是同一文件时（交付链形态），记为
   `instruction_reuse="already_in_workspace"`，不写盘。
4. 数据门：开启 staging 必须声明 `instruction_data_class`，按
   `validate_data_boundary` 判定，**不通过即拒绝**。
5. 指令上下文发现：每次调用都枚举 OpenCode 实际会合并的 `AGENTS.md` 集合并记
   sha256，进收据（`instruction_context_*`）。这是真正的缺口——**可追溯性**，不是
   注入。没有它，"这次调用没有指令"和"这次调用有指令但没人记录"长得一模一样。

**`core/miner_pool/providers/opencode_cli.py`**：显式 `instruction_mode="off"`，
附理由。该链已有 `govern_model_messages()` 注入的受治理 system contract，再叠
20KB 人工 MD 是第二个未受治理指令面，且会把未分级内容推过只管 messages 的数据门。

**`core/instruction_boundary.py`（新增）：指令出站门**

分级不再由调用方声明，改为受治理台账裁决——调用方自报分级正是让未标记的
PRIVATE 文件溜出去的东西。

- `08_GOVERNANCE/instruction_data_classes.json`：逐个指令文件的分级台账。**缺条目
  不是许可**，未分级即阻断。
- `08_GOVERNANCE/sanitizer_receipts.jsonl`：append-only 凭据，按
  `artifact_sha256` 绑定文件当前哈希。改一个字节，旧凭据立即失效。
- 判定规则：未分级 → 阻断；`PRIVATE`/`CORE` → 阻断（无凭据可解锁）；`CAPABILITY`/
  `STRUCTURE` → 需要有效凭据；`PUBLIC` → 放行。
- 分级只是答案的一半：放行前对**实际将外发的字节**重跑
  `validate_data_boundary(target="MODEL_CONTEXT")`，所以 `PUBLIC` 标签不能豁免
  凭据形状内容。

**`ops/test_opencode_instruction_staging.py`**：19 例，覆盖 staging 全部性质 +
出站门的未分级阻断、local-only 阻断、条件类缺凭据阻断、有效凭据放行、凭据随文件
改动失效、`PUBLIC` 标签不豁免凭据内容、阻断时子进程数为 0。
相关全量回归见第 8 节。

## 6. 明确没做的事

- 没有在任何生产路径开启 staging。
- 没有改模型路由、没有改 `ace_daemon.py`、没有改宪法文件。
- 没有改写 `docs/ACE_OMX_ADAPTATION_DECISION_20260905.md` 中"拒绝自动注入
  `AGENTS.md`"的已登记决策——那是主 steward 的记录，不是本改动的权限。
- 没有把 `--auto` 写进适配器。权限放开是独立决策。
- 没有回头篡改任何历史收据。

## 7. 分级裁决落地后的直接后果

主 steward 裁决：生产 `AGENTS.md` 归 `PRIVATE`，不得改标 `PUBLIC`；出站必须带
有效 sanitizer receipt；**在这道门生效前不得继续把未脱敏的 PRIVATE 指令送往
托管模型**。门已生效，实测（`_seal_verification.py`，不发任何内容）：

| 场景 | 判定 | 子进程 |
| --- | --- | --- |
| 生产 `C:\tmp\ace_core\AGENTS.md` | `BLOCKED` `local_only_class:PRIVATE` | 0 |
| 交付形态工作区（含同一文件） | `BLOCKED` 同上 | `attempts=0` |
| **交付链真实 cwd `C:\tmp\ace_core`** | `BLOCKED` 同上 | `attempts=0` |
| 聊天链隔离临时目录 | `ALLOWED` | 正常 |

**交付链现在被门挡住**，这是裁决的直接结果，不是回归。它的收据会返回
`opencode_instruction_gate_blocked` 与完整判定，不启动任何子进程。恢复交付需要
以下之一，且都是独立决策：

1. 产出经批准的指令 sanitizer，并为精简版 `AGENTS.md` 签发凭据（凭据声明的是
   **脱敏后**的分级，且该分级自身必须可出站）；
2. 交付链改用不含 PRIVATE `AGENTS.md` 的工作目录；
3. 一次显式的分级裁决。

不涉及该数据外发的免费模型工作未被波及，符合裁决第 4 条。

**`ops/audit_instruction_egress.py`（新增）：只读审计**

门只能在即将发起调用时给出判定，而"从这里发起会发出什么"原本只能靠真发一次来
回答——恰恰是最需要预判的那种。该审计不调模型、不联网，只回答三件事：

1. 本 checkout 出货了哪些 `AGENTS.md`，各自是否有分级记录（未分级 → FAIL；
   未分级文件是门本身永远暴露不出来的那一类问题，它在有调用落到它头上之前是惰性的）；
2. 从给定工作目录发起是否放行；
3. 哪些调用点当前被挡、按哪条规则。

任一调用点被挡或存在未分级出货文件即返回非零退出码，可直接用作门禁。

本机实测：

```
shipped AGENTS.md: 1
  PRIVATE  C:\tmp\ace_core\AGENTS.md
BLOCKED  delivery stage cwd (production repository root)
ALLOWED  chat route temp workspace (instruction_files=0)
```

`instruction_evidence_keys()` 经由 `core/delivery_execution` 解析而非复制清单，
避免审计与落盘收据对"哪些字段承载判定"产生分歧。

## 8. 拒绝必须可读（`d386634`）

门挡住之后，拒绝原本会被逐层削弱成"worker 失败"：

| 层 | 原本 | 现在 |
| --- | --- | --- |
| `worker_verdict()` | 收据压缩成 `{"ok","error"}`，丢掉文件/分级/规则 | 按白名单携带指令证据（不整份复制） |
| `WorkerRouter.run()` | 门拒绝与模型无关，却走完整个 fallback 链 | 遇到 `BLOCKED` 立即停止 |
| `classify_failure()` | 记成 `worker_failure`，像模型抖动 | 独立分类 `instruction_gate_blocked` |
| 聊天 provider | 空回复被报成 `opencode_empty_reply` | 透传判定 |

普通失败不受影响：非零退出仍会走完整个模型序，有测试钉住这条边界，防止捷径扩大
成"一律不重试"。

## 9. 嵌套指令洞：已实测确认并封堵（`55ac3ea`）

V2 会在 agent **读取某个子目录**时加载那个子目录的 `AGENTS.md`。而门此前只枚举
"工作目录向上"这一条链——和交付链那个洞是同一类，说明"覆盖全部"的承诺当时
**并不成立**。

实测（修复前，真实调用）：顶层 `AGENTS.md` 写明"这里没有口令"，子目录
`notes/AGENTS.md` 才有口令。让模型先读 `notes/readme.txt` 再回答口令问题，
**口令原样返回**，而门只看到了顶层那一个文件。10.2 秒，1 次工具调用，门判
`ALLOWED`。嵌套内容进入了模型上下文，从未被分类。

哪些嵌套文件会被加载取决于 agent 决定读什么，**事前不可知**，所以现在全部枚举。
这是刻意保守的代价：运行中从未碰到的嵌套文件，也可能挡住一次本会干净的调用。
扫描上限 5 万目录，触顶时以 `instruction_scan_incomplete` **阻断**而不是报告
部分集合——不完整的枚举就是一个未分类的指令面，却穿着"已检查"的收据。

嵌套文件在收据中记为 `origin: nested`，祖先文件与工作目录自身区分开，读者能
判断每个文件为何被纳入。

## 10. 交付形态的指令加载已实测（关闭原开放项 1）

V2 对"工作区在 home 之外"的规则是停在 project root，这和先前已验证的临时目录
分支不是同一条代码路径，所以交付形态此前只有推论、没有实测。

在一个**同形态的一次性 git 仓库**里实测（生产工作区全程未作为 cwd 使用）：

| 项 | 值 |
| --- | --- |
| `git rev-parse --show-toplevel` | 临时仓库根 |
| 门判定 | `ALLOWED` |
| 上下文发现 | 仓库根 `AGENTS.md`，sha256 `d7e51fa6…` |
| nonce 是否命中 | **是** |
| 是否使用工具 | **否** |
| 耗时 | 5.4s |

结论：**project root 形态下 `AGENTS.md` 确实作为指令注入**，与临时目录形态一致。

这条证据的用处在于把问题收窄：交付链被挡**纯粹是分级问题，不是机制问题**。
加载路径已被证明可用，唯一拦住它的是 `C:\tmp\ace_core\AGENTS.md` 的 `PRIVATE`
判定。恢复交付因此只需要解决分级，不需要碰机制。

仍未验证且刻意不验证的一项：生产 `AGENTS.md` 的**内容**是否真的影响了交付产出。
要证明它必须在生产工作区跑模型，而那会让模型有机会改动生产状态——为一份好奇心
付这个代价不可接受。原开放项 1 就此降级：机制已实测，内容影响未测且不测。

## 11. 脱敏路径已落地并实测（主 steward 裁决）

裁决：原始 `AGENTS.md` 保持 `PRIVATE`，不批准外发，不允许改标 `PUBLIC`；但只要能
证明实际发送的是合规脱敏版本，可沿现有交付链继续。

**先补了一个洞。** 裁决要求"为脱敏结果提供有效 sanitizer receipt"，但当时门对
receipt 的校验只检查 artifact 哈希匹配 + `data_class` 通过边界。这不足以支撑裁决：
`validate_data_boundary` 检查的是**被告知的分级**，不是内容来源，所以一张
`data_class: PUBLIC` 的 receipt 签在**未经删改的私有字节**上会顺利通过——门被开了，
而一个字节都没删。

现在 receipt 必须：`source_path` 指向台账中已注册的源；`source_sha256` 与
`artifact_sha256` **不同**（否则说明没删任何东西）；源必须本身受限；降级方向只能是
降低。违反时 receipt 被拒绝，但**不掩盖**台账已有的判定，理由记在
`ignored_receipt` 字段里随行。

**脱敏工具** `ops/sanitize_instruction_file.py`：按 section 白名单裁剪，脱敏前后
各跑一次校验，写出产物 + 追加 receipt。私有仓名 / 组织名 / 本机路径即使在保留
section 内部也会被替换成 `[private repo]`——section 级丢弃会连同工作规则一起丢掉。

**实测结果**（原始文件哈希前后一致，未被改写）：

| 项 | 值 |
| --- | --- |
| 源 | `AGENTS.md` 20703 B，`PRIVATE`，sha `857af1ac…` |
| 产物 | `model_instructions/AGENTS.md` 5574 B（减少 15129 B） |
| 产物分级 | `PUBLIC`，`basis: sanitizer_receipt`，`source_data_class: PRIVATE` |
| receipt | `R-AGENTS-9f4ab4fe`，绑定源/产物双哈希 |

裁决四项条件逐条实测通过（`_verify_e2e.py`，无模型调用，门在任何子进程之前判定）：

1. 原始 `AGENTS.md` 仍 `PRIVATE`、仍 `BLOCKED`、`attempts=0`、文件哈希未变；
2. 脱敏产物凭 receipt `ALLOWED`，`basis=sanitizer_receipt`；
3. 实际发送集合中无 `PRIVATE`/`CORE` 文件；
4. 篡改产物（追加伪 api_key）后重新 `BLOCKED`，`attempts=0`——门没有被放宽。

## 12. 交付链已改走脱敏指令（真实调用实测通过）

裁决的最后一个开关。交付链原本以**仓库根**为工作目录，而私有手册就在那里——
门会正确地拒绝它。现在每次交付尝试：

1. 先探测脱敏产物是否可用（`model_instructions/AGENTS.md` 是否存在、门是否放行），
   不可用则**根本��构建 worker**，交付如实停在 `NO_WORKER_AVAILABLE`；
2. 建临时暂存目录，只放脱敏后的 `AGENTS.md`；
3. 模型在暂存目录里写，**只有声明的 `required_path` 被复制回仓库**（逃逸路径直接
   拒绝）；模型写在别处的文件不会被带回，也无法影响下一次尝试；
4. 暂存目录无论成败都删除。

**探测必须发生在暂存目录，不能在产物原位。** `model_instructions/` 在仓库内部，
OpenCode 会从工作目录向上把私有手册一起加载，于是门会以"与脱敏无关的理由"
拒绝。探测时先复制到仓库外的临时目录，判定的才是模型真正会看到的集合。

**receipt 改为按内容哈希绑定，不再按路径。** 相同字节就是相同内容，与它被复制到
哪个暂存目录无关；要求路径相符会迫使 receipt 写下一个尚不存在的暂存路径。

真实调用实测（真实 `opencode.exe`，无 mock）：

| 项 | 值 |
| --- | --- |
| 门 | `ALLOWED` |
| 指令分级 | `PUBLIC`，`basis: sanitizer_receipt`，`source_data_class: PRIVATE` |
| 工作目录 | `%TEMP%\ace_delivery_stage_*`，非仓库根 |
| 产物 | `docs/E2E_REDUCED_INSTRUCTIONS_PROOF.md` 508 B，落在声明路径 |
| raw output 含私有内容 | **否** |

`ops/test_delivery_reduced_instructions.py` 6 例钉住：脱敏不可用则不建 worker、
被拒调用不落产物、只复制声明路径、逃逸路径拒绝、暂存目录必删、交付验证仍在仓库
根找到产物。相关回归 **90 passed**。

## 13. 脱敏对模型可见内容的影响（实测）

原开放项"内容差异对交付质量的影响未测"分两半测：删掉了什么、模型现在还能用什么。
第二半无法用"对比两次交付产出"回答——那需要一个拿私有手册当对照组的实验，而
对照组本身就是被禁止的外发。所以改为直接测可见性。

### 13.1 静态：删掉了什么

源 20255 B → 保留 5265 B，**移除 74%**；19 个 section 保留 3 个
（Identity / Core Principles / Engineering Rules）。

按"祈使句"统计（must / never / always / do not / should）：

| | section 数 | 祈使句 |
| --- | --- | --- |
| 保留 | 3 | 2 |
| 丢弃 | 16 | 6 |

丢弃中仍带指令的 section 有 5 个：**search policy、daily self-loop、
model strategy、autonomous acceptance is owned by the main steward、
free zone to reality bridge**。其余 11 个（仓库地图、三层架构、运行时组件、
已知缺口等）是描述性内容，没有祈使句。

**取舍已修正**：`autonomous acceptance is owned by the main steward` 原本被丢弃，
而它带 2 条祈使句——它规定"谁有权验收"。这是最该保留的治理约束之一，第一版白名单
漏了它。现已并入 `DELIVERY_KEEP_SECTIONS`（`ops/sanitize_instruction_file.py`
里的一个常量，避免白名单散落在命令行历史里），产物 5574 B → 6730 B，凭据
`R-AGENTS-9f4ab4fe` → `R-AGENTS-3424d623`。两条 receipt 都在 append-only 台账里。

### 13.2 行为：模型还能用什么

真实脱敏产物经门放行后暂存提问，8 题各半来自保留/丢弃 section，全程无工具兜底
（工具会让模型读到私有手册，测出脱敏没挣来的命中）。

```
kept content available to the model    : 4/4
dropped content available to the model : 0/4
private repository name recovered      : False
```

被丢弃内容的实际表现：`Search Policy` 层序、`Model Strategy` provider 顺序均答
`UNKNOWN`；私有仓名未出现，模型只说"private repo"。

保留内容全部可得：`Identity`（用户角色）、`Continuity Principle`、`Recovery First`、
`Engineering Rules` 的 reuse-first——注意模型是**意译**而非照抄（答
"Never build what already exists in the repository" 而非 "reuse first"）。

判读更正一处：`Architecture` 顶层一题我起初记为 MISS→命中"母亲版"，
实为模型从**保留的 Core Principles** 里取的词，答的是保留内容，与被丢弃的架构
章节无关。分离是干净的。

**结论**：模型拿到的是完整的 ACE 职责与工作规则（Identity + Core Principles +
Engineering Rules），丢掉的是描述性上下文与两段治理/路由细则。私有内容确实
出不去。

## 14. 指令暂存是否值得：一个被推翻的结论

我写了 `ops/measure_instruction_value.py`，想回答一个该被问的问题：这么多机制，
指令到底改变了什么。第一轮结果很诱人——保留规则的 trace「有指令 2/2、无指令 0/2」。

**那个表是错的，而且错得有意思。** 对照组产出 0 字节，所以它的 trace 全 0 只是
因为没有文档可扫。"有文档 vs 没文档"衡量的是这一臂是否成功，不是指令是否让产出
更好。

追下去发现的是一个我自己引入的回归：对照组是**真失败**
（`opencode_all_models_failed`、`changed=False`、工作区空的），模型在空暂存目录里
翻找 miner pool 代码直到预算耗尽，一句话没说。

根因：交付链原本以仓库根为工作目录，模型能读代码。我把工作目录换成只含
`AGENTS.md` 的暂存目录后，**模型看不见它要写的那个代码库了**。我用"内容不出库"
换掉了"能读库"，而且没意识到这是笔交易。暂存是为了满足分级裁决，改法本身没被
单独质疑过。

**修法**：暂存目录里写一份作用域精确的 `opencode.json`——对仓库路径
`external_directory: allow` + `read: allow` + `edit: deny`，别的一律不管。任务里
明说代码在哪儿可读。

验证：实跑 18 次工具调用全部 `completed`，模型成功读到暂存目录之外的代码
（`ops/test_delivery_repo_read_access.py` 6 项断言：交付物落位、读开、写禁、
作用域只含仓库、任务里指路）。

### 仍未解决：模型探索到预算耗尽

读权限修好后，探索本身成了新瓶颈。实测同一任务：模型 18 次工具调用全成功读完
仓库，最后一句是"Now let me write the file"——**预算耗尽，一行没写**。

这是能力/预算问题，不是权限问题，我没有处理。交付超时率若上升，看这里而不是看
权限。可选方向（都未做）：给暂存目录预置一份相关文件的只读子集以减少探索轮次；
或按任务类型缩短 worker 的探索预算。这两项都会改变交付语义，属于独立决策。

## 15. 一个测量工具连续骗了我五次

第 14 节那个测量脚本，我改了五版才拿到一次能站住的数字。过程比结论更值得留下——
**五次失败是同一个模式**。

| # | 声明的契约 | 实际 |
| --- | --- | --- |
| 1 | 两臂可比 | 两臂 prompt 不同 |
| 2 | 测生产 | harness 重实现暂存逻辑，成了影子 |
| 3 | `test_*.py` 是测试 | 是脚本 + `sys.exit`，破坏全套件收集 |
| 4 | 对照合法 | 用未分级文件当对照，被门全拦下 |
| 5 | 测生产 | harness 给 1/3 的超时预算 |

四次栽在"**harness 冒充生产，但实际是另一个东西**"；第 3 次不同，是**文件命名冒充
测试**。共同根因：**我比较的是 harness 与 harness，从没验证过 harness 与生产一致**。

**第一次**：表 looked惊人（五项 trace 全 +2）。其实对照组产出 0 字节，它的 0 只是
"没有文档可扫"。"有文档 vs 没文档"衡量的是这一臂有没有成功，不是指令好不好。
我看到整齐的 +2 没有先去查对照臂是否真的跑过。

**第二次**：修好生产路径的读权限后，我**没有同步测量脚本**——它自己重写了一遍暂存
逻辑，于是继续跑着那个坏掉的对照组，而我准备拿它的输出当结论。修了生产，不等于
修了影子。

**第三次**：脚本终于**正确地拒绝出结论**（两臂都没写出文档 →
`NO USABLE COMPARISON`）。这是它第一次做对。但同一份输出暴露了对照组本身是错的：
control 3/3 `gate=BLOCKED`、`0.0 秒`——**一次模型都没跑**。我拿未分级的
`AGENTS.md` 当对照，而未分级正是门存在的意义；而且台账按路径后缀匹配，固定路径的
登记条目永远匹配不上随机命名的暂存副本。这一版是对的形状、错的对照。

### 三个教训

**一、效应大得可疑时，先查某一臂是不是失败了。** +2/+2/+2/+1/+2 这么整齐，第一
反应应该是"太干净了"，不是"结论很强"。

**二、测量工具和生产路径会漂移。** 工具自己重实现生产逻辑，就是给自己造了一个不会
跟着 bugfix 一起修的影子。要么直接调生产函数，要么明确声明"我测的不是生产"。

**三、对照组先问"当前系统里什么才是合法对照"，不要先造一个再调试它跑起来。** 我
花了两轮让一个错误的对照"跑通"；第一轮就问"门会不会放行它"，答案是不该早点发现。

固化下来的防护（不是靠记性）：脚本现在在评分前做硬断言——**任一臂被门拦下就拒绝
出结论**，因为门拦下意味着模型从未运行，那一臂的 0 不是证据；**对照臂若携带了指令
文件也拒绝**，因为携带指令的对照不是对照。两臂的任务提示词与生产逐字相同，超时不再
显式传入而是走生产同一个默认值，差异只剩 AGENTS.md 这一个文件。

### 第五次：harness 给的预算是生产的 1/3

第四版的两条硬断言都过了（6/6 `gate=ALLOWED`、对照臂 `instruction_files=0`），却仍然
`NO USABLE COMPARISON`：对照 3/3 写不出文档。查下来是我的 harness 传了
`timeout_seconds=300`，而生产 `_delivery_worker_runner` 用 `OpenCodeWorker()` 默认
**900s**。所谓"探索到预算耗尽"，大部分是我自己压出来的。

修法是**不传** `timeout_seconds`，让两臂和生产走同一个默认值。改完第一次出现两臂
都能产出：

| | 指令 | 对照 |
| --- | --- | --- |
| 产出文档 | **3/3** | 1/3 |
| 平均体量 | 8714 B | 7377 B |
| reuse-first trace | 3/3 | 1/1 |
| find-before-build | 1/3 | 0/1 |
| recovery-first | 1/3 | 0/1 |
| acceptance-path | 1/3 | 0/1 |

**怎么读这张表**：完成率 3/3 vs 1/3 是最实的信号——它说明之前记录的"模型探索到
预算耗尽"这个瓶颈，有相当一部分是测量工具制造的，不是生产的。

trace 不能过度解读。对照那一臂唯一产出的文档**也命中了 reuse trace**，说明该 trace
有假阳性：模型会自发说 "reuse existing"。所以 reuse 那行的 +2 不能算指令的功劳。
剩下三项方向一致但 n=3，Fisher 精确检验 p ≈ 0.43，**统计上不显著**。

诚实的结论：**完成率有差异，文档内容差异未达显著**。要判定后者需要 n≥8 且 trace
判据改掉假阳性。这些都没做。

## 16. 仍然开放

1. **交付链的指令上下文**：机制已在同形态仓库实测为可用（第 9 节）。未验证的
   只有"生产 `AGENTS.md` 的内容是否影响了产出"，为它跑生产工作区模型不可接受，
   不测。`docs/REAL_CLI_DELIVERY_PROOF.md` 已被删除，协议 231 行引用的证据在磁盘
   上已不可核验。
2. **指令对产出质量的影响仍未定论。** 第 15 节测出完成率 3/3 vs 1/3，但文档内容差异
   n=3 不显著，且 reuse trace 有假阳性（对照也会自发命中）。要判定需要 n≥8 且改掉
   判据，未做。"完整手册 vs 脱敏版"的 A/B 仍是禁止的外发，做不了。
3. **trace 判据本身不可靠。** 模型会自发说出"reuse existing"之类的话，关键词命中不等于
   规则生效。要更硬的判据（例如让模型在不读指令时明确答错），未设计。
4. **保留白名单的增删需要重签 receipt**。每次改动 `DELIVERY_KEEP_SECTIONS` 都会
   改变产物哈希，旧 receipt 立即失效（这是按哈希绑定的设计意图）。`ops/verify_reduction.py`
   用于在改动后确认新产物确实在模型上下文里、且私有内容仍出不去。
3. **跨目录读取**：需要读工作区之外文件的非交互调用会被 `ask` 挡下并自行拒绝。
   交付链不受影响；受影响的调用若存在，需要显式的权限策略，而不是加 `--auto`。
4. **临时目录的祖先指令面**：聊天链的工作区在 home 之内，V2 会向 home 方向合并
   `AGENTS.md`。收据会显式记录生效集合，将来有人在 `C:\Users\Administrator\` 放
   指令文件会被看见（并因未分级而阻断）而不是静默并入。