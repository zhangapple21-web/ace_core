# ACE 自主进化实验：Authority Boundary

## 1. Candidate Invariant

**Fresh Capability Causality（FCC）候选不变量：**

> 任何会改变 Runtime 生命周期的动作，必须能沿一条可复核、当前有效且范围受限的因果链回溯到 ACE Runtime 的权威接口：`Admission → TaskPool transition → owner/lease/claim/fencing`。缺少其中任一环节时，输入只能是观察、建议、证据或错误记录，不能产生 Runtime 写入；进程、终端、Codex 窗口、manifest、report、receipt、model output 或成功的 HTTP 响应本身都不授予该能力。

这条候选规则可以同时解释本轮多个现象：

- 非 owner、缺失/异常 owner、过期 TTL 必须 `read_only` / `STALE_HINT_ONLY`，而不是 takeover；
- `PASS`、`APPROVE`、`COMPLETED`、`delivery_approved=true` 只能留在派生记录层；
- 3002 的一次 HTTP 200 只能证明该探针成功，不能替代 3000、旧会话或 heartbeat 归属证据；
- 400、断线或无 receipt 的重试不能自动获得新的执行权；
- 自动派单只能声明项目/任务范围，不能因为绑定了某个终端或线程就成为 Runtime owner。

**本轮裁决：INCONCLUSIVE（候选成立但未全局证明）。**

已覆盖的 TaskPool、Admission、manifest guard、TTL/fencing 与派生记录攻击样例支持该候选；但旧 `core/scheduler.py` / `core/task_queue.py` 仍在 checkout，所有窗口写入点没有全量 guard 证明，heartbeat 实际线程归属未闭合，3000 的 500 也未定位。因此只能说“已覆盖路径的边界更严格”，不能说整个 checkout 已满足 FCC。

## 2. Counterexamples

1. **测试契约漂移（已复现）：** 当前直接运行 `ops/test_runtime_authority_audit.py` 得到 `22 passed, 5 failed`。失败均发生在 `TaskPool.create_task(..., creator="test")` 尚未进入攻击断言之前，当前默认构造要求 `task_admission_required`；旧测试假定 test creator bypass。由此，报告中先前“攻击测试通过”的结论不能直接视为当前可复现证据。它反例化了“测试绿色等于边界已验证”。

2. **旧生命周期仍可被触达（未排他证明）：** `core/scheduler.py` 与 `core/task_queue.py` 源码仍存在。未知 CLI 已 fail-closed 是一条已覆盖边界，但没有 syscall/ACL/全仓库调用图证明外部脚本不能直接写旧队列。因此“只有 TaskPool 能改变状态”在全 checkout 范围仍是 UNKNOWN。

3. **窗口 guard 覆盖率未知：** `active_work_manifest` 的 `access_mode()`/`require_write_access()` 规则本身严格，但尚未证明每个窗口工具、脚本、编辑器集成和自动化写文件前都调用 guard；只读协议存在不等于所有写路径受其保护。

4. **调度归属不闭合：** 活跃 cron 是 project-scoped；`automation` 等 heartbeat 没有本地文件可证明的 `target_thread_id`。因此当前不能排除调度上下文变化造成重复观察、旧窗口继续写入或 owner 漂移。

5. **双端口反例：** 3002 `/healthz` 与 `/v1/models` 成功，而 3000 `/health`、`/v1/models` 仍为 500。一个健康端口的成功不能推出所有历史会话、旧路由或 heartbeat 使用同一能力链；“系统恢复”与“全路径闭合”是两个命题。

6. **派生记录重解释风险：** 当前攻击样例未发现 manifest/report/model output 自动改变 TaskPool，但未来 runner 若把 receipt、report 或 model output 重新解析为 command，FCC 会被破坏；本轮没有全仓库未来路径证明，因此保留为待证反例。

## 3. Next Experiment

执行一个**只读/临时目录的 Capability-Chain Closure Matrix v1**，不改生产代码、不删除 legacy、不写入真实 TaskPool：

1. 用有效 admission 在临时 TaskPool 建立 fixture，逐一测试 `create → claim → renew → move/update/recovery`；每次记录 state hash、owner、claim_id、fencing_token 与 reason。
2. 对同一 fixture 注入六类伪造输入：manifest `COMPLETED`、report `delivery_approved`、decision/model `PASS/APPROVE`、缺失 owner、过期 TTL、旧 claim/旧 fencing；预期均为 Runtime hash 不变，并得到显式 read-only/stale/reject 结果。
3. 对所有已发现的写入口建立清单：TaskPool、legacy scheduler/task_queue、`agent_team` writer、automation runner、heartbeat runner。逐入口标记 `OBSERVED_GUARD / NO_GUARD_EVIDENCE / DIRECT_WRITE / UNREACHABLE`；不能观测的路径结论只能是 `INCONCLUSIVE`。
4. 对自动派单分别记录 `project_id / target_thread_id / terminal-or-window evidence / task owner`，构造旧窗口、非 owner、TTL 过期和重复触发场景；预期只能观察或建立 disjoint declaration，不得重复 claim/takeover。
5. 将 3000 与 3002 分开做最小健康与失败注入，检查 400/500/断线/无 receipt 时是否产生任何新 task、claim、renew 或重试副作用；预期是 fail-closed，不能以另一端口成功代替本端证据。

**裁决规则：**

- `PASS`：每个可达写路径都要求完整 capability chain；无 capability 的攻击只留下观察/错误记录，Runtime hash 不变。
- `FAIL`：任一未持有有效 admission、owner/lease/claim/fencing 的输入改变 Runtime，或任一派生记录/端口成功直接触发 claim/renew/完成。
- `INCONCLUSIVE`：路径未能实体化、线程归属不可证明、旧队列可执行性未决；不得把缺证据改写成 PASS。
