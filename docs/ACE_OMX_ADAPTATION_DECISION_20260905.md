# OMX（oh-my-codex）适配决策 — 2026-09-05

## 来源与边界

本文评估腾讯云文章《oh-my-codex 上手：给 Codex 加一层工作流和团队运行时》
（<https://cloud.tencent.com/developer/article/2689454>）中介绍的
`Yeachan-Heo/oh-my-codex` 思路。本文是一次本地、只读为主的架构对照，落地内容
仅限本决策记录和操作约定；不安装 npm 包，不修改 ACE 生产代码，不启动新的
Scheduler、Router、Worker、TaskPool 或通知链路。

## 已核对的事实

- 文章把 OMX 定位为 Codex CLI 外的一层工作流/运行时，主要入口是
  `$deep-interview`、`$ralplan`、`$ralph`、`$team`。
- 文章描述的安装/初始化会写入全局 prompts、skills、Codex 配置、项目
  `AGENTS.md`，并建立 `.omx/`（plans、logs、memory、runtime state）。
- 文章描述的 `$team` 依赖 tmux/psmux，并带有 leader/worker、共享任务队列、
  mailbox、claim/status/resume/shutdown 等运行时语义。
- 当前机器上 `codex` 可用（`codex-cli 0.153.0-alpha.5`），但 `omx`、`tmux`
  和 `psmux` 均未发现；当前 Codex 配置使用既有 Responses 兼容路径，通知 hook
  明确关闭。
- 当前 ACE 已有唯一的 `ace.py daemon --serve`、既有 TaskPool/admission/
  validator/governor/archivist 生命周期，以及仅用于 Codex/人类协作元数据的
  `agent_team/active_work_manifest.json`。
- 当前全局路由技能已经规定：先检查需求与边界，再决定直接执行或路由后台任务；
  路由任务须健康探针、单写者、主 Agent 验收，不能成为 ACE 生产控制面。

## 适配结论

| OMX 机制 | 决策 | 当前落点 | 冲突边界 |
| --- | --- | --- | --- |
| `deep-interview`：先澄清需求、非目标和边界 | **吸收** | 继续使用当前对话澄清、Environment First、`continue_gate` 和任务包边界 | 不新增命令或强制模型调用 |
| `ralplan`：执行前形成可审计计划 | **吸收** | 复用现有 `agent_team/task-board.md`、`docs/superpowers/specs/`、验收路径和 handoff receipt | 不建立 `.omx/plans` 第二事实源 |
| `ralph`：同一 owner 持续推进到完成 | **适配** | 复用现有 Codex task 生命周期和 ACE 单 daemon；长任务按现有 continue-before-work 协议切换上下文 | 不自动重放 `UNKNOWN`/无 receipt 动作，不增加常驻 loop |
| `team`：并行 worker、队列、mailbox、恢复/清理 | **适配** | 复用 Codex App 后台 task、`agent_team` 声明和单写者规则；主 Agent 独立验收 | 不引入 tmux/psmux、共享队列或第二 Scheduler/TaskPool |
| `.omx/` plans/logs/memory/runtime state | **拒绝** | 继续以 ACE 的 `runtime/`、既有 docs、`agent_team/*/state.json` 和 manifest 为事实源 | 防止状态、所有权和恢复语义分叉 |
| 自动生成/注入项目 `AGENTS.md` | **拒绝** | 保留人工审阅的当前 `AGENTS.md` 与全局技能 | 自动改写会扩大隐式指令面，且可能覆盖 ACE 约束 |
| `doctor` / `HUD` / `explore` / `sparkshell` | **吸收语义** | 分别映射到现有 continuity/runtime audit、status summary、`rg` 只读检索和有边界的 shell 验证 | 不为别名再造一套诊断 runtime |
| OpenClaw notification/webhook 集成 | **暂缓/拒绝作为默认** | 维持当前 notify 关闭和主 Agent 外部发送边界 | 外部通知是副作用，不因 OMX 安装自动开启 |

## 已落地的最小操作约定

对需要正式交付的 Codex 工作，默认采用以下顺序，但不要求安装 OMX：

```text
澄清目标/非目标
  → 写出最小计划与验收条件
  → 判断直接执行还是 Codex 后台并行
  → 按单写者/receipt 规则执行
  → 主 Agent 独立验证、采纳或拒绝
```

对 ACE 生产运行，仍以原有生命周期为准：

```text
Environment → Observe → Audit → Recovery → Discovery → Candidate →
Task → Validator → Governor → Archive → Evolution → Heartbeat
```

两条链路共享“先澄清、再计划、再执行、再验证”的工作顺序，但不共享第二套
任务队列、状态目录或权限模型。

## 明确不做的动作

- 不执行 `npm install -g oh-my-codex`，不运行 `omx setup`。
- 不修改 `C:\Users\User\.codex\config.toml`、全局 prompts/skills 或当前项目
  `AGENTS.md`。
- 不安装 tmux/psmux，不创建 OMX 共享队列、mailbox 或常驻团队 runtime。
- 不把文章中的“workflow/runtime”描述当成 ACE 已验证能力；如未来要评估，
  必须先做独立源码/版本/兼容性核验，再以研究记录进入现有审阅链。

## 后续使用规则

当任务只是单文件小改、状态查询或强顺序排障时，直接由当前 Agent 完成；只有
真正独立且并行收益明确的工作才使用现有 Codex 路由技能。任何跨窗口接管先读
`active_work_manifest` 和现有 receipt；过期 TTL 只产生观察提示，不自动接管。

本决策不改变 ACE 的生产权威、数据门、Advisor/Risk/TG 边界，也不产生新的
模型调用或后台任务。
