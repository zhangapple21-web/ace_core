# Runtime Authority Boundary Audit v1

审计日期：2026-09-06（Asia/Shanghai）
范围：`ace.py`、`ace_daemon.py`、`core/task.py`、Admission/TaskPool 路径、`agent_team/` 协作元数据、Codex 路由配置、当前自动化、3000/3001/3002 本机端口、OneAPI 模型目录预检与 workspace 写锁。

## 结论摘要

- **唯一已验证的现代生产运行时与 Runtime Authority：** `C:\tmp\ace_core\ace_daemon.py` 的 `AceDaemon`。它承载生产 daemon 生命周期；`TaskPool` 负责任务状态、lease、claim、fencing、recovery，Admission 负责任务准入。
- **自动派单绑定关系**：当前 6 个活跃 cron（`ace`、`ace-09-45`、`ace-2`、`ace-3`、`ace-4`、`ace-6`）配置为 `target.type=project`，绑定项目 `a5014012-497b-475f-b1ad-4afdeca9e980`，不是某个具体终端。带 `target_thread_id` 的 heartbeat（`ace-5`、`agnes`）目前均为 PAUSED。活跃 heartbeat `automation` 与 `tg-companion-overnight-check` 未在 TOML 中声明 `target_thread_id`，其实际运行线程归属未由本地文件充分证明，记录为 **UNKNOWN/RISK**，不能声称已完成稳定 owner 绑定。
- **跨窗口 owner 协议**：`agent_team/active_work_manifest.json` 与 `active_work_manifest.py` 已要求 `owner`、TTL、单窗口 owner；非 owner、owner 缺失/畸形、非 active、TTL 过期均为 read-only；TTL 只产生 stale hint，不自动 takeover/claim/renew。该文件仍是协作元数据，不是 ACE lease。
- **本轮发现并修复的真实缺口**：`TaskPool.move_task()` 旧路径可把 `pending` 直接写成无 owner/claim 的 `active`，且对已有 active lease 的 stale 对象缺少与 `stored.claim_id` 的强制比较。现在兼容调用会原子生成 lease/claim/fencing，已有 lease 必须匹配 claim/fencing 才可写。
- **本轮追加修复**：未知 `ace.py` 命令此前会落入历史 `core.scheduler.Scheduler` 初始化；现在未知命令在导入旧运行时前直接 fail-closed。`active_work_manifest` 拒绝空白 owner；`TaskPool.claim_task/renew_lease` 拒绝空白 owner/claim 与非正 TTL，避免形成无主或立即失效租约。
- **本轮追加修复**：独立验收 checker 不再只信任外部 `protocol_receipt.valid=true`；现在强制回执 `task_id` 与协议版本绑定到被验收 task，拒绝携带 errors 的回执，并独立重查 envelope 的 start protocol、complexity、pipeline、events 结构，防止跨任务伪造回执或空/畸形 envelope 的 active 记录被验成 PASS。
- **本轮已验证收口**：已发现的 legacy Python 生命周期入口 `core.scheduler`、`core.task_queue`、`04_PROTOCOLS/heartbeat` 均 fail-closed；旧源文件保留用于考古，不把此修复扩大为任意脚本/文件系统的 ACL 级封锁。
- **heartbeat 单一 owner：** 生产 heartbeat 固定为 `owner=ace_daemon`，并携带当前 `run_id`；历史 protocol heartbeat 不再可执行，不能形成第二循环。
- **workspace 写入序列化：** `AceDaemon` 在 daemon 生命周期内获取并释放 `.workspace.write.lock`。锁冲突返回 `workspace_write_locked` 以及 `owner`、`run_id`、`lock_file`、`recommendation`；malformed lock fail-closed。
- **Provider 与模型目录边界：** 3000 LiteLLM/OneAPI 与 3002 Responses 兼容层分别报告，不能互相掩盖；当前两个 catalog 都包含 `gpt-5.6-sol`。`OneAPIProvider` 与 SurvivalLoop 的 OneAPI 路径均在 `/chat/completions` 前查询 `/models`，未知模型返回不可重试的 `model_unavailable`。
- **不能声称的内容：** 本审计没有证明整个 checkout 已消除所有第二生命周期、所有隐式写路径或所有窗口工具的文件级 owner guard；也没有把独立端口的当前 catalog 推广为永久健康承诺。

## 事实矩阵

| 对象 | 当前作用 | 可直接改变 Runtime | 权威性 |
|---|---|---:|---|
| `AceDaemon` | 唯一现代生产 daemon 生命周期、heartbeat owner、workspace 写锁生命周期 | 是 | YES（唯一现代生产运行时） |
| `TaskPool` | 由 AceDaemon 使用的任务生命周期、lease、claim、fencing、recovery | 是 | YES（任务状态权威） |
| Admission / `validate_admission` | 任务进入 TaskPool 前的准入 | 间接 | YES（准入边界） |
| `agent_team/active_work_manifest.json` | Codex/人类窗口声明、范围冲突提示 | 否 | NO |
| `agent_team/*/state.json` | durable 协作记录、thread/output 追踪 | 按现有定义仅记录 | NO |
| Report / Daily Shift | 派生观察 | 否 | NO |
| Receipt / Decision Record | 执行证据/决策证据 | 否 | NO |
| Model Output / role metadata | 建议、分析、能力提示 | 否 | NO |
| Codex window metadata | 外部协作上下文 | 否 | NO |

## Owner、TTL 与跨窗口

已验证：`active_work_manifest.py` 的 `validate_entry()` 要求 owner；`access_mode()` 对 missing/invalid owner、非 active、stale、other window 返回 `read_only`；`conflict_hints()` 只返回 `COMPARE_THEN_SPLIT_OR_WAIT` 提示，不写 TaskPool。`active_work_manifest.json` 当前唯一条目已是 completed，owner 为 `codex-window-root`，`production_integration=false`、`taskpool_authority=false`、`automatic_takeover=false`。

未证明：所有可能的窗口脚本/编辑器写入操作都调用 `require_write_access()`；因此不能把协议函数存在等同于全工具覆盖。

## Runtime 状态与攻击式测试

已运行并通过：

1. 伪造 manifest `COMPLETED`、report `delivery_approved=true`、model output `PASS`：TaskPool 状态不变。
2. 删除 owner、TTL 过期：原窗口及其他窗口均 read-only，未发生 takeover/renew。
3. Finance 0/1/2/3 候选：分别得到 `NO_VALID_EVALUATION_PICK`、`VALID`、`VALID`、`INVALID_EXCESS_EVALUATION_PICK`，未生成 synthetic pick/task。
4. stale claim 不能覆盖新 owner；无效状态转换被拒绝；Archivist 没有 guardian decision 不能归档。
5. 新增测试验证 `pending→active` 兼容路径必有 owner/lease/claim/fencing；stale 对象不能重写 active 任务。

## 自动化盘点

- 保留：`ace`（09:00 晨间金融观察）、`ace-2`（09:30 开盘验证）、`ace-09-45`（09:45 只读能力日报）、`ace-3`（12:30 午盘）、`ace-4`（15:15 收盘）、`ace-6`（18:30 Free Zone 隔离班次）、`ace-world-atlas-daily-archaeology`（09:00 只读考古）、`automation`（每小时值班/夜班协调）、`tg-companion-overnight-check`（每3小时健康巡检）。这些提示均声明不新建第二套 Scheduler/TaskPool/Router，不降低门槛；但 09:00 的 `ace`、World Atlas heartbeat、`automation` 存在时间/观察重叠，当前证据不足以安全合并或关闭。
- 已暂停且无需再运行：`ace-5`（旧 Responses continuation 400 记录）、`agnes`（一次性冷却重试完成后暂停）、`automation-3`（每周回顾）。本轮未误删任何活跃自动化；当前目录实查共 12 项，不能将早先的 10 项清单当作当前全集。
- 风险：`automation` 是 heartbeat 但无 `target_thread_id`；其 owner/线程归属需通过 Codex App 运行记录继续验证，不应假定绑定某终端。

## 端口、进程与 HTTP

- 3000：LiteLLM/OneAPI。必须独立报告 health、catalog 和请求结果，不能由 3002 覆盖；当前已验证 catalog 包含 `gpt-5.6-sol`。`OneAPIProvider` 与 SurvivalLoop OneAPI 路径在 `/chat/completions` 前先验证 `/models`，未知模型返回不可重试的 `model_unavailable`。保留端口自身诊断为独立风险。
- 3001：无监听（连接被拒绝）。
- 3002：Responses 兼容层。必须独立报告 health、catalog 和请求结果，不能由 3000 覆盖；当前已验证 catalog 包含 `gpt-5.6-sol`。当前 `C:\Users\User\.codex\config.toml` 的 `base_url=http://127.0.0.1:3002/v1`、`wire_api="responses"`、`notify=[]`，符合当前 Codex 路径。
- ACE daemon：唯一现代生产运行时为 `AceDaemon`。daemon state、`.workspace.write.lock` 与 heartbeat 共享当前 `run_id`；生产 heartbeat 为 `owner=ace_daemon`，并含 `run_id`。daemon 生命周期获取并释放 workspace 锁；冲突返回完整 `workspace_write_locked` 诊断，malformed lock fail-closed。

## 仍存在的缺口 / 不作过度修复

1. `core/scheduler.py`、`core/task_queue.py`、`04_PROTOCOLS/heartbeat.py` 已对已发现的 legacy 生命周期入口 fail-closed；仍未证明任意外部脚本都无法直接写旧队列、TaskPool 或其他共享文件，也未做全仓库 syscall/ACL 级排他证明。
2. 生产 Admission 已收紧，不能由公开配置、creator 字符串或 CLI 启用缺失 Admission；测试边界不构成生产写入口。后续仍应防止新的测试便利接口泄漏到生产 API。
3. `DailyShift`/Report/Receipt 等写入是派生记录；本审计只证明已测攻击不会自动驱动 TaskPool，不证明每个未来脚本都遵守该契约。
4. 3000 与 3002 的健康、catalog 和请求结果均须独立复核；虽当前两侧 catalog 都包含 `gpt-5.6-sol`，但这不能替代各自端口的持续健康诊断。
5. 近期心跳历史记录显示 2026-08-29 曾有 Windows `WinError 5` 状态替换失败；现有 `_save_state` 已有有界重试，当前 heartbeat identity 与 owner 已验证，但未进行长时间压力复现，因此不能称永久消除。
6. `.workspace.write.lock` 只序列化已接入 daemon 生命周期的写入；malformed lock 已 fail-closed，但未把直接文件系统写入转化为 OS ACL 保护。

## WHY THIS DESIGN COULD STILL FAIL

- 某个新脚本可能绕过 `TaskPool`，直接写 `task_pool/*` 或旧 `task_queue` 文件；当前没有全仓库 syscall/ACL 级封锁。
- 某个窗口可能只读取 manifest 的 owner 字段，却不调用 guard，继续写共享文件；owner guard 覆盖率仍是 UNKNOWN。
- Receipt、Report 或 Model Output 若被未来 runner 重新解释为 command，仍可能形成隐式第二事实源；本轮只验证已覆盖的攻击样例。
- `update_task()` 对无 lease 的 pending 元数据仍允许受控更新；若未来把此接口暴露给不可信调用方，需增加调用者级别/字段级白名单，而不是依赖约定。
- 自动化 cron 是 project-scoped，heartbeat 可能是 thread-scoped 或缺少显式 thread owner；若调度器上下文改变，可能出现重复观察或 owner 归属漂移。
- 3000/3002 双路由并存，配置、环境变量和历史线程可能指向不同端口；一次 3002 成功不能证明 3000 或所有旧会话都健康。

## 验证记录

本次复核还发现并修复了一个真实的恢复边界回归：同一任务短暂同时出现在
`pending/` 与 `active/` 时，旧的 `_find_task_file()` 只按 Windows 文件系统
mtime 选记录；粗粒度时间戳可能让观察结果退回 `pending`，从而把“孤儿 active
记录不可推进”的测试误判成另一状态。现在按持久化 `updated_at`、纳秒 mtime 和
确定性的生命周期顺序选择记录；这只是恢复读取判定，不会升级状态或创建第二生命
周期。新增重复状态文件回归后，相关 authority/owner/manifest/legacy 组为
`72 passed`，修复提交为 `2b7b8b8`，已推送到 `origin/main`。

- `ops/test_runtime_authority_audit.py`：7 passed。
- `ops/test_independent_acceptance.py ops/test_execution_discipline.py ops/test_runtime_authority_audit.py`：24 passed；另有 legacy CLI/owner/admission 回归 20 passed，临时跨进程 `ops/run_ace_start_acceptance.py`：`PASS`。
- 追加回归：`ops/test_runtime_authority_audit.py`、`ops/test_legacy_cli_fail_closed.py`、`ops/test_active_work_manifest.py`：22 passed；覆盖未知命令不加载旧 Scheduler、空白 owner/租约参数拒绝。
- `ops/test_24h_runtime_mainline.py`：88 passed（含 lease/recovery/fencing/state-machine）。
- `ops/test_active_work_manifest.py`、`ops/test_task_admission.py`、`ops/test_legacy_cli_fail_closed.py`：17 passed。
- 交叉回归：TaskPool/non-convergence/continuity/discovery 35 passed；Daily Shift/Finance/Model Discovery 38 passed；runtime claim/continue-gate/trace 13 passed；quality/admission 14 passed。
- `python -m py_compile core/task.py ops/test_24h_runtime_mainline.py ops/test_runtime_authority_audit.py`：通过。
- 全量 `pytest`：`744 passed`；`compileall`：通过；`git diff --check`：仅报告既有 EOF 空行和一处既有尾随空格。

结论标签：`RUNTIME_BOUNDARY_CLOSED / PARTIALLY_VERIFIED / REMAINING_RISKS_RECORDED / NO_CLAIM_OF_GLOBAL_ACL_ELIMINATION`。
