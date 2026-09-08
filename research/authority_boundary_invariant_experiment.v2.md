# 1. Candidate Invariant

## Fresh, Attributable, Non-Escalating Capability（FANCE）

> 任何输入只有在能够沿一条**当前新鲜、主体可归属、范围受限、可独立重放**的能力链到达 ACE Runtime 权威写接口时，才可以改变 Runtime 生命周期。能力链至少要包含：有效 Admission、目标 TaskPool transition、稳定 owner、未过期 lease、匹配的 claim/fencing，以及可定位的实际写入口。缺一项时，输入只能保持为观察、建议、证据、错误记录或 `NO_NEW_WORK`；它不能靠“内容看起来像完成/批准”、成功的 HTTP 响应、终端/窗口绑定、历史绿色测试、Manifest、Report、Receipt、Decision Record、Model Output 或 Learning/Slice 记录自行升级成 Runtime command。

这条候选不变量比“TaskPool 是唯一权威”更高一层：它同时约束**状态**和**证明状态的证据**。它可以解释本轮多个现象：

- 非 owner、缺失/异常 owner、过期 TTL、旧 claim/fencing 只能 `read_only` / `STALE_HINT_ONLY`，不能 takeover、claim 或 renew。
- `PASS`、`APPROVE`、`COMPLETED`、`delivery_approved=true` 只能是派生记录；只有经过现行 Admission 与 TaskPool 权威接口的动作才是生命周期事实。
- 3002 的一次 `200` 只证明该探针成功，不能证明 3000、旧会话或 heartbeat 的能力链也成功。
- 一个历史报告或“测试通过”摘要，如果不能在当前 checkout 用同一入口重放，就只能是旧证据，不能证明当前边界。
- Slice、Learning、Report 或 Consumer 观察可以提出下一实验，但不得成为第二 Scheduler、第二 TaskPool 或隐式生产写入者。

**裁决：INCONCLUSIVE。** 当前已覆盖路径支持 FANCE，但没有全 checkout 的排他证明；因此本轮只能确认“已覆盖路径的边界更严格”，不能声称整个 checkout 已消除所有第二生命周期或所有隐式写路径。

# 2. Counterexamples

1. **已修复的证据漂移（FACT）：** 本轮首次直接运行 `ops/test_runtime_authority_audit.py` 得到 `2 passed, 5 failed`。5 个失败都在 `TaskPool.create_task(..., creator="test")` 的 fixture 创建阶段触发 `task_admission_required`，尚未进入对应攻击断言；这反例化了“旧绿色摘要等于当前边界已验证”。随后仅修正测试夹具，使其显式提供完整 Admission（未放宽生产准入），同一套测试当前重放为 `7 passed`。因此旧摘要已被重新核验，但该修复只覆盖测试证据漂移，不扩大为全 checkout 安全证明。

2. **旧生命周期仍存在（FACT；全局可达性 UNKNOWN）：** `core/scheduler.py` 与 `core/task_queue.py` 仍在 checkout；`ace.py` 对未知/旧 CLI 已 fail-closed，但没有 syscall、ACL 或全仓库调用图证明任意外部脚本不能直接导入旧实现或写旧队列。因此“全 checkout 只有 TaskPool 能改生命周期”仍未证明。

3. **窗口 guard 覆盖率 UNKNOWN：** `active_work_manifest` 的 owner/TTL/access-mode 规则本身严格，但尚未证明每个窗口工具、脚本、编辑器集成和自动化在写共享文件前都调用 `require_write_access()`。协议存在不等于所有写路径受保护。

4. **调度归属 UNKNOWN：** 活跃 cron 的配置是 project-scoped；`automation` 等 heartbeat 没有本地 TOML 证据表明固定 `target_thread_id`。因此不能排除调度上下文变化、旧窗口继续写入、重复观察或 owner 漂移。

5. **双端口反例（FACT）：** 3002 的 `/healthz` 与 `/v1/models` 成功，而 3000 的历史探针仍出现 `500`。一条端口的成功不能替代另一条端口、旧会话或 heartbeat 的新鲜能力证据；400/断线/无 receipt 的重试也不能自动获得执行权。

6. **Slice/Consumer 叙事尚未被当前运行态支持（FACT + UNKNOWN）：** 当前 TaskPool 实时目录为 `pending=0, active=0, review=0, approved=0, blocked=139, archived=576, graveyard=17`。附件两份文档中关于“持续堆积、缺少全局 Consumer、需要 Nightly Slice”的内容属于候选解释，不是当前 Runtime 证据；若直接据此新增 Slice runner，反而可能形成第二 Scheduler/TaskPool。当前只能把“消费责任和整体认知是否存在缺环”列为待验证问题。

7. **派生记录重解释风险（HYPOTHESIS）：** 已测攻击没有让 Manifest/Report/Model Output 改变 TaskPool，但未来 runner 若重新把 Receipt、Report、Learning 或 Model Output 解析成 command，FANCE 会被破坏。本轮没有全仓库未来路径证明，故不能把“尚未发现”写成“不会发生”。

8. **独立验收回执绑定缺口（FACT → PATCHED）：** 初始 checker 只信任外部传入的 `protocol_receipt.valid=true`，没有强制回执 `task_id` 与被读取的 task 相等，也没有再次确认 task 自身存在 execution-discipline envelope。伪造“另一个任务的 valid 回执”或“同任务的空 envelope”是可构造的证据链反例。现已在 `ops/independent_acceptance.py` 增加任务身份、协议版本/start protocol、receipt errors，以及 complexity/pipeline/events 的最小结构重查，并加入回归攻击；该补丁只收紧验收证据，不改变 Runtime 状态机。

# 3. Next Experiment

执行一次**Capability-and-Consumer Closure Matrix v2**。只使用临时目录和只读生产观察；不改生产代码、不删除 legacy、不暂停或新增自动化、不写入真实 TaskPool。

1. **建立可重放 fixture（部分完成）：** 已在 `ops/test_runtime_authority_audit.py` 的临时 `TaskPool` fixture 中提供完整、有效的 Admission，并验证派生记录、owner/TTL、move、stale claim、orphan recovery 和 Finance 0/1/2/3 攻击路径；当前回归为 `7 passed`。仍需补齐同一 fixture 的逐步 state hash/入口记录，以及 `create → claim → renew → move/update → recovery` 的完整矩阵，不能把这 7 个测试等同于全路径闭环。

2. **运行非升级攻击：** 对同一 fixture 注入伪造 Manifest `COMPLETED`、Report `delivery_approved=true`、Decision/Model `PASS/APPROVE`、缺失/空白 owner、过期 TTL、旧 claim/fencing、成功但无 receipt 的 HTTP 重试。每个攻击的 PASS 条件是 runtime hash 不变，并得到 `read_only`、`STALE_HINT_ONLY` 或明确 reject；任何 claim/renew/transition 都是 FAIL。

3. **建立写入口矩阵：** 对 `core.task.TaskPool`、`core/scheduler.py`、`core/task_queue.py`、`agent_team` writer、automation runner、heartbeat runner 和已发现的 ops 脚本逐入口标记 `OBSERVED_GUARD`、`DIRECT_WRITE`、`NO_GUARD_EVIDENCE` 或 `UNREACHABLE`。静态存在但无法实体化的路径保持 `INCONCLUSIVE`，不得按“没有运行”推成安全。

4. **验证 Consumer 而不制造工作：** 仅在临时 TaskPool 放入一个带 admission 的 synthetic fixture，观察唯一 daemon/Researcher 是否能发现、claim、完成或明确返回 `NO_NEW_WORK`；记录真实调用链和 owner。生产快照若仍无 executable pending，只记录“当前无消费对象”，不为证明活跃而创建生产任务。Slice 只能作为观察/归纳输出，不能直接入池或触发调度。

5. **验证窗口与自动化归属：** 对每项 automation 记录 `kind / project_id / target_thread_id / terminal-or-window evidence / owner evidence / last-run evidence`。构造非 owner、旧窗口、过期 TTL、重复触发的只读场景；预期是观察或 disjoint declaration，不得 takeover、renew 或重复 claim。无 thread 证据的 heartbeat 保持 `UNKNOWN`。

6. **分端口失败注入：** 分别探测 3000、3002 以及当前 Codex `base_url`；在 400、500、断线和无 receipt 条件下检查是否产生 task、claim、renew、重试副作用。不得用 3002 的成功覆盖 3000 的未知，也不得把一次成功请求升级为全链路健康。

**当前重放证据：** 独立验收、执行纪律和 Runtime authority 攻击回归合计 `24 passed`；另有 legacy CLI/owner/admission 回归 `20 passed`。`ops/run_ace_start_acceptance.py` 在临时 TaskPool 中返回 `verdict=PASS`、`authority=ACE_TASKPOOL`、`runtime_mutation_by_checker=false`。这只证明临时、已覆盖的 start/acceptance 路径。

**裁决规则：**

- `PASS`：每个可达写路径都有完整 FANCE 能力链；无能力攻击只留下观察/错误记录，Runtime hash 不变；Consumer 证据能追到唯一 daemon/TaskPool。
- `FAIL`：任一无 admission、owner/lease/claim/fencing 的输入改变 Runtime，或派生记录、Slice、端口成功、旧窗口/heartbeat 直接触发 claim/renew/完成。
- `INCONCLUSIVE`：路径无法实体化、线程归属不可证明、legacy 可执行性未决、测试 harness 与生产契约不一致，或只能观察到结果而不能追到写入口。
