# Continue-Before-Work Protocol v1

## 固化原则

系统在“继续工作”之前，必须先证明三件事：

1. **上下文可靠**：当前上下文有明确身份、预算仍安全、不是从旧失败状态盲目续跑。
2. **协议可靠**：提供方、接口和 continuation 能力已确认；提供方降级时必须有已验证 fallback。
3. **证据可靠**：上一动作有可追溯 receipt；没有 receipt 的外部提交、未知结果或被中断动作不得自动重试。

任一项证明缺失，状态即为 `CLOSE_AND_HANDOFF`：停止当前长回合，写入最小 handoff receipt，保留 `UNKNOWN`/`FAILED`，并转入新上下文。不得重复同一个问题、不得凭文件存在声称成功、不得通过新增 Scheduler/Router/运行时绕过边界。

## 统一决策

`C:\tmp\ace_core\core\continue_gate.py` 是无模型、无网络、无副作用的判定函数。它只返回 `CONTINUE` 或 `CLOSE_AND_HANDOFF`，不替调用方执行动作。调用方应把判定结果和以下字段写入已有 receipt/ledger：

```json
{
  "contract_version": "continue_before_work.v1",
  "context_id": "...",
  "provider": "...",
  "interface": "...",
  "action_id": "...",
  "decision": "CONTINUE|CLOSE_AND_HANDOFF",
  "reason_codes": [],
  "prior_attempt_status": "PASS|FAILED|UNKNOWN|NO_RECEIPT",
  "next_context_required": true
}
```

## 三个系统的直接吸收

当前运行时的业务适配仍以 ACE daemon、DramaAI 视频入口、Infinite Canvas 工作台为主；但门禁继承不再依赖开发者显式调用：

- Python 解释器通过用户级 `sitecustomize.py` 自动安装 `continue_gate_runtime`，覆盖 ACE、Video Kingdom、FastMovieAI 及其子目录中的新脚本；关闭状态会在 `subprocess.Popen`、`socket.connect`、`http.client.connect`、`os.system` 等外部边界抛出阻断异常。
- Infinite Canvas 在 `main.tsx` 启动时安装全局 `fetch/XHR` 守门，新增页面、路由和 API helper 默认共享同一浏览器状态。
- ACE daemon 每次边界判定都发布 `runtime/continue_gate_runtime_state.json`；新进程读取该事实源，先收口再等待 `python -m continue_gate_runtime new-context` 创建新上下文。

因此新增入口不需要记住调用点，但必须运行在受保护进程/工作台中；绕过启动钩子、设置 `CONTINUE_GATE_BYPASS=1` 或直接在未受保护环境运行，均属于显式运维例外，不能作为生产默认路径。仅在文档、配置或 receipt 中声明“已接入”仍不算运行时接入。

### ACE

- 在生命周期边界和恢复前调用 gate；`CONTINUITY_DEGRADED` 或运行时身份未 attested 时只留审计 receipt，不重放任务。
- 将 `UNKNOWN`、`NO_RECEIPT`、`REPEATED_FAILURE_LIMIT` 作为不可自动清除的状态，交给下一上下文重新核验。
- 继续沿用一个 daemon、一个 TaskPool、一个现有 evidence bridge；本协议不是第二套调度器。

### Free Zone

- 每轮先 sense，再决定是否继续；没有 resident trace、hash 绑定或真实实验 receipt 时，允许保持 idle，但不伪造活动。
- 新实验可以显式声明 `allow_empty_for_new_experiment=true`，但实验结束必须生成 receipt；失败、沉默、漂移和半成品全部保留。
- 任何 Free Zone 结果仍是 `RESEARCH_ONLY`，不能因 gate 通过而自动进入生产。

### Video Kingdom / DramaAI

- 每个镜头提交前检查上下文和 provider capability；没有 `video_id`、没有 HTTP/content-type 验证或没有抽帧 receipt，就不轮询、不重提、不把静态图当动作片。
- 连续性、音频、字幕、首中尾帧检查仍由现有 preflight/quality gate 负责；本协议只决定“是否还有资格继续下一步”。
- 长任务按镜头/阶段切换上下文，交接只携带 manifest、hash、失败原因和下一步，不携带整段工具输出。

## 本次故障的对应修复

本次会话暴露的是“新窗口不等于新鲜上下文”：旧任务、浏览器内容、构建日志和重复接管都被继续累积；同时 Shenwen/LiteLLM 返回 400 且无 fallback，最后仍尝试继续。未来应在接管、工具异常、重复失败和上下文接近阈值时触发 `CLOSE_AND_HANDOFF`，而不是再次问同一个问题。

审计量化：被接管的旧任务单次请求最高约 `178,510` input tokens（记录的模型窗口 `258,400`），累计 input 约 `220,786,165`；接管它的“新”窗口自身累计约 `8,471,734` input tokens、`105` 次自定义工具调用，并出现被中断的回合。它们证明的是长上下文与重复编排风险，不证明已经越过硬上限；因此门禁使用“接近阈值即收口”，而不是等到上游拒绝后再重试。
