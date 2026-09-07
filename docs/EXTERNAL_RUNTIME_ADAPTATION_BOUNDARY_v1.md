# External Runtime Adaptation Boundary v1

状态：`ACTIVE` · 适用：任何外部 Agent Workflow / Runtime / Harness 项目

## 目的

把外部项目当作机制样本，而不是 ACE 的第二个控制面。协议只允许把经核验、
可复用的机制映射到现有 ACE/Codex 协作规范；不因“有新玩法”而复制实现、
创建新运行时，或改变 ACE 的生产权威。

## 固定评估顺序

1. **核验来源、版本和实际能力**：优先读官方源码/发布页/锁定提交，再对照本地只读探针；文章、README 和宣传语只能作为待核验线索。
2. **提取机制，不复制实现**：记录它解决的协作问题、输入/输出和失败语义，不搬运命令、目录、队列或 hook 实现。
3. **映射现有能力**：逐项检查 ACE/Codex 是否已有等价能力、权威、状态源和验收路径。
4. **作出一个明确决策**：
   - `ABSORB`：机制已与现有边界兼容，只沉淀原则/提示。
   - `ADAPT`：机制有价值，但必须复用现有 owner、状态源、gate 或生命周期。
   - `REJECT`：与现有权威、连续性或安全边界冲突，或只是重复造轮子。
   - `DEFER`：证据、兼容性或真实缺口不足，保留问题但不进入运行时。
5. **只有真实缺口才进入后续实验**：实验必须另有范围、证据、回滚和主 steward 验收；本协议本身不创建任务或实验。

## 不可越过的边界

- 外部 Runtime 永远不能成为 ACE Runtime Authority；ACE 的唯一生产 daemon、既有生命周期和既有 gates 保持权威。
- 外部状态目录（例如 `.omx/`）不得自动成为第二事实源；计划、日志、记忆、运行态必须映射到已有受治理的 ACE/Codex 记录，或明确 `REJECT`。
- 外部 Scheduler、Queue、Ownership、Claim/Lease、Recovery、Gate 默认拒绝；只有证明现有能力存在真实缺口，且通过独立实验和主 steward 验收，才可讨论适配。
- 外部 hooks、通知、webhook、插件或自动 setup 不得自动改写 `AGENTS.md`、配置、权限、通知链或生产状态。
- “命令可用”“目录存在”“doctor 通过”不等于 ACE 运行时能力已被证明；必须保留证据边界和 `NOT_PROVEN` 项。

## 统一登记字段

每个外部项目一条 append-only JSONL 记录，至少包含：

```json
{
  "external_runtime": "<canonical project name>",
  "source": ["<official source URL>", "<secondary source URL if used>"],
  "version": "<release/tag or UNKNOWN>",
  "commit": "<full commit or UNKNOWN>",
  "verified_at": "<ISO-8601 with timezone>",
  "capability_summary": ["<verified mechanism 1>"],
  "decision": "ABSORB|ADAPT|REJECT|DEFER",
  "mapped_existing_mechanism": ["<ACE/Codex owner or mechanism>"],
  "conflict_boundary": ["<explicit non-adoption or authority boundary>"]
}
```

缺失的版本、提交、实际调用或兼容性证据必须写成 `UNKNOWN` / `NOT_PROVEN`，
不得用推断填空。记录是评估凭证，不是外部 Runtime 的配置入口、调度入口或
第二事实源。

## 本次唯一实例：oh-my-codex（OMX）

实例记录见 [`external_runtime_adaptation_register.jsonl`](./external_runtime_adaptation_register.jsonl)。
核验结论：源码仓库为 `Yeachan-Heo/oh-my-codex`，当前公开 release `v0.21.3`，
核验提交 `2da36489cfa07ef1df802f01865e7d959d36f236`；README/仓库结构实际展示
了 workflow skills、`.omx/` 持久状态、Codex hooks/plugin、以及 tmux/psmux-backed
team/worktree 运行时语义。文章中的 `$ralph` 等入口不是当前 README 的完整现行
主链（当前主链包含 `$autopilot` 与 `$ultragoal`），因此文章只作为线索而非版本
契约。本文仅吸收“先澄清→再计划→按 owner 执行→验证”的机制，适配到现有 Codex
task/receipt/主 steward 验收；`.omx/`、外部队列/ownership/scheduler、自动 setup/
通知链均不进入 ACE。
