# ACE 本体与可替换连接层恢复

ACE 是以电脑为物理基座、以连续性为核心的智能运行时。项目、任务、记忆、经验、治理、恢复与进化的权威归属 ACE；模型是外部能力，MCP 是连接管道。连接层的在线、目录健康或模型响应不能证明 ACE 的运行连续性。

本文件不创建新的 daemon、TaskPool、治理入口或调度器，也不宣称自主闭环已验证。

## 权威与远程真源

- 核心：`https://github.com/zhangapple21-web/ace_core.git`，使用既有恢复入口。
- 连接层：`https://github.com/zhangapple21-web/ace-host-adapter-lab.git`。
- ACE 自持有的来源清单：`recovery/companion_runtime_manifest.json`。当前连接层固定 commit `85b9fbdbfdefadb86dba846f2282a49892162a63`。
- `.venv`、宿主注册、凭据与活跃租约不能通过 clone 自动恢复；不复制旧 PID/租约作为新实例的活性证据。

## 新电脑恢复

在包含本次改动的 ACE checkout 中，用 Python 3.11 执行：

```powershell
py -3.11 recovery/restore_from_remote.py --workspace-root D:\ACE-Restored --with-bridge
```

目标必须为空。既有流程先恢复核心/私有状态并执行 bootstrap；随后可选恢复 Bridge，checkout 固定 commit，创建独立 venv，安装 requirements，生成目标机器路径的 `ACE_MCP_CONFIG.json`。不会自动注册宿主、启动 MCP、启动/重启 daemon，也不会下载凭据。

默认不带 `--with-bridge` 时保持原核心恢复行为；外部连接层不成为 ACE 生存依赖。请求连接层恢复但失败时，整个请求报告 FAIL，按既有流程保留产物和失败收据；不删除核心。`--state-url ""` 仅恢复代码，不能称为恢复同一个连续运行体。

将生成的 MCP 配置导入所选宿主即可连接；PI 原生插件需要另行注册仓库的 `pi-plugin` 开发目录，并映射 Python、adapter、capsule 与 ACE root。PI 包装包含 worker-capsule 变更入口，不应因名称 Read-only 就授予额外权限。

## 验证边界

本轮离线测试检查恢复顺序、固定版本验证、依赖失败、目标路径配置生成，以及原恢复器行为。未执行真实远程整包恢复、私有状态恢复或新电脑演练。

迁移后的连续性仍须使用既有 continuity audit、heartbeat/进程关联、任务状态转移及 lineage 收据证明。目录存在的 health 只能证明布局，不证明 daemon 活性；快照不能单独证明正在运行。下一阶段验收问题仍为：此刻是否活着、正在做什么、为什么阻塞、上一轮发生了什么。

本次改动在 commit/push 前仅存在于本地；远程 clone 不会自动获得这些新恢复功能。
