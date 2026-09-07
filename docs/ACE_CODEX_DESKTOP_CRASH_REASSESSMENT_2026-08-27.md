# Codex Desktop 崩溃复盘（2026-08-27）

## 结论先行

刚才的复现没有启动 ACE 的第二个 daemon，也没有启动 R1/R2 的旧 loop、Advisor、Telegram 或模型任务。主进程 `ace.py daemon --serve` 仍在运行；测试进程已经不存在。问题发生在 Codex Desktop 的会话/工具收尾链，ACE 代码不是直接故障点。

本轮比昨天多出一条可定位证据：

```text
Custom tool call output is missing for call id: ...
```

该错误在 12:37–12:39 的同一会话中重复出现。与此同时，Remote Control WebSocket 每秒重复记录：

```text
remote control requires ChatGPT authentication; API key auth is not supported
```

这说明桌面端在处理工具输出/会话收尾时，仍被 Computer Use / Remote Control 链牵连。知乎文章提供的“Desktop 外壳与 app-server 分离、先看日志再按错误族处理”的方法是有参考价值的；文章本身不是本机事实源。

## 本机只读诊断

| 检查 | 结果 | 判断 |
| --- | --- | --- |
| `Get-AppxPackage *Codex*` | 单一包 `OpenAI.Codex 26.820.7780.0` | 未发现多个已安装商店包 |
| `USERPROFILE` | `C:\Users\User` | 纯 ASCII，不符合文章中的非 ASCII 用户目录分支 |
| `where codex` | 当前指向 `...d0097be4feba73d0\codex.exe` | 当前 CLI 可解析 |
| 当前 CLI | `codex-cli 0.150.0-alpha.8` | CLI 二进制可执行 |
| 当前进程注入的 PATH 中 Codex 目录 | 同时有 `...b91d382ea836415f` 与 `...d0097be4feba73d0`；用户持久 PATH 中没有 Codex 项 | 这是 Desktop 运行时注入的旧目录风险，不应修改系统 PATH |
| 旧 `b91...` 目录 | 只有 `rg.exe`，没有 `codex.exe` | Desktop 注入的旧运行时目录不完整 |
| `CODEX_CLI_PATH` | 指向当前 `d009...\codex.exe` | Desktop 有显式路径，但仍不能证明收尾链无故障 |
| `config.toml` `notify` | 仍指向 `codex-computer-use.exe ... turn-ended ...` | 与“API-key 会话无法使用 Remote Control”形成直接冲突 |
| ACE daemon | `ace.py daemon --serve` 进程存在且响应 | ACE 主运行态未因这次测试退出 |
| pytest | 当前没有残留 pytest 进程 | 测试本身不是正在占用资源的后台进程 |

## 这次到底运行了什么

本轮实际运行过：

1. R1/R2 只读考古清单与自由区考古班次；
2. 新增的 8 个针对性测试（通过）；
3. 一次 `python -m pytest -q --disable-warnings` 全量测试；该命令在约 41% 后长时间运行，随后被停止。

没有运行：

- `ace.py daemon --serve` 的启动或重启；
- `mine-seed` 旧 `daily_self_loop.py`、`heartbeat.py`、`autonomous_loop.py`；
- Stock Advisor、Telegram、broker 或自动下单；
- Computer Use 命令本身。

## 根因分层

### 已有本地证据支持

1. **Desktop 的 Remote Control/Computer Use notifier 仍在工作**：配置中的 `notify` 与 API-key 认证边界冲突，日志持续重试。
2. **工具输出收尾出现缺失结果**：`Custom tool call output is missing` 是本轮新出现的直接会话层错误，足以解释“运行任务时窗口突然异常”，但不能把它归因给 ACE 测试逻辑。
3. **Desktop 运行时 PATH 存在旧不完整 Codex 目录**：与知乎文章的 PATH 残留分支相符，但用户持久 PATH 是干净的，因此不应通过修改系统 PATH 处理；目前 `CODEX_CLI_PATH` 指向新目录，所以它更像潜在放大器而不是已证明的唯一根因。

### 当前没有证据支持

- 非 ASCII 用户目录；
- 当前商店包数量冲突；
- `defaultPrompt` 超过 128 字符的插件缓存崩溃；
- 香港 IP、腾讯/东方财富接口或 ACE 数据源导致 Desktop 退出。

## 暂不执行的动作

本轮没有删除系统 PATH、卸载商店包、清空插件缓存或重启 Desktop。已在备份后把 `config.toml` 的 `notify` 改为空列表；该设置会在下一次 Desktop 会话中生效。

## 推荐的安全顺序

1. **短期**：不要再从 Desktop 发起全量长测试；在普通终端用当前 CLI 跑小范围测试，避免触发 Desktop 收尾钩子。
2. **PATH 不改系统设置**：用户持久 PATH 已经干净；旧 `b91...` 是 Desktop 当前进程注入的运行时目录，等待 Desktop 自身修复，不通过系统环境变量硬改。
3. **先处理 Computer Use 链**：已备份 `config.toml` 并将 `notify` 明确设为空列表。下次 Desktop 启动后观察它是否再次自动写回；如果写回，说明 Desktop 的自动修复逻辑在覆盖用户配置，应继续使用 CLI 或切换到支持 ChatGPT 身份认证的会话。
4. **最后再验证插件缓存**：只有日志明确出现 `defaultPrompt` / `code=1` 等插件清单证据时，才按文章的修复 5 处理；当前没有这条证据，不应先清缓存。

## ACE 侧处理

ACE 继续保持唯一 daemon、严格 Data Health/Admission、自由区 `PROPOSAL_ONLY` 和每日考古自动化。本轮新增加的 R1 生态宪法种子是惰性的自由区资产，不会被 Desktop 收尾链调用，也不会触发生产任务。
