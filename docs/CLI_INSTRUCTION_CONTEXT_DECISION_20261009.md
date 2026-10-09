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

## 8. 仍然开放

1. **交付链的指令上下文存在，但从未被证明**。cwd 即仓库根意味着真实
   `AGENTS.md` 在被加载；这来自 V2 机制的推论，未在生产工作区跑模型实测。
   `docs/REAL_CLI_DELIVERY_PROOF.md` 已被删除，协议 231 行引用的证据在磁盘上已
   不可核验。
2. **跨目录读取**：需要读工作区之外文件的非交互调用会被 `ask` 挡下并自行拒绝。
   交付链不受影响；受影响的调用若存在，需要显式的权限策略，而不是加 `--auto`。
3. **临时目录的祖先指令面**：聊天链的工作区在 home 之内，V2 会向 home 方向合并
   `AGENTS.md`。收据会显式记录生效集合，将来有人在 `C:\Users\Administrator\` 放
   指令文件会被看见（并因未分级而阻断）而不是静默并入。