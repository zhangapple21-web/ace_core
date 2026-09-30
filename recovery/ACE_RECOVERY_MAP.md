# ACE Recovery Map（灾备与一键复活基线）

> 基线日期：2026-09-30（Asia/Shanghai）
> 状态：`BACKUP_COMPLETE / RECOVERABLE`。远程 ref 已验证，最终隔离 clone 已按恢复链跑通；外部 Provider 和私有素材仍按人工清单补回。

## 0. 先读结论

- **当前核心真源**：`ace_core`（ACE 认知运行时、AceDaemon、TaskPool、Worker/lease/fencing、Researcher/Validator/Guardian/Archivist、MemoryGateway/MemoryIndex、协议、schema、恢复与测试）。
- **视频能力域**：`ace-video-kingdom`（视频控制面、生产门禁、模型/能力路由、角色/场景/镜头合同、视频侧测试和规则）。它不是 ACE 本体，不能替代 `ace_core`。
- **可选能力资产**：`ace-video-assets`（已发布的公开参考资产）、`R1_continuity_archive`（考古知识）；`mine-seed-credentials` 只存私密凭据，不进入公开恢复链。
- **3000 / 3002**：按本基线均视为废弃历史路径，不是灾备恢复依赖；恢复后不得把它们重新声明为生产入口。
- **私密依赖**：API key、Token、密码、浏览器凭据、机器密钥、私有参考图/音视频、CosyVoice 权重和本地运行缓存均不进公开 Git。它们必须按 `SECRET_REQUIRED` / `HUMAN_REQUIRED` 清单从安全来源补回。

## 1. 新机器恢复顺序

1. 安装 Git、Python 3.11+、PowerShell 7（或 Windows PowerShell 5.1）。
2. 拉取核心仓库的**指定真源分支**（见 `REPOSITORY_MAP.md`），不要默认猜 `main`。
3. 在核心仓库根目录执行：
   - Windows：`pwsh -File recovery/bootstrap.ps1 -WorkspaceRoot <新机器工作区>`
   - 仅有 Python：`python recovery/bootstrap.py --workspace-root <新机器工作区>`（若存在）
4. bootstrap 会：检查 Git/Python；生成 `ace_config.local.example.json` 和安全配置目录；创建可重建的运行目录；不下载密钥、不启动旧端口；运行 compile/import/基础测试；输出 `HUMAN_REQUIRED`。
5. 按 `MISSING_HUMAN_REQUIRED.md` 从安全来源注入凭据和私密资产；**只设置环境变量或本机私密目录，不把它们写回 Git**。
6. 先运行 ACE 健康检查和 TaskPool lease/fencing 测试，再按需启动 `AceDaemon`。生产 heartbeat 只走当前 `AceDaemon`；旧 heartbeat/scheduler/3000/3002 历史入口不恢复为生产依赖。
7. 如需视频能力，再拉取 `ace-video-kingdom` 指定分支并按其 README/`docs/` 入口执行；媒体 Provider 不是恢复演练的前置条件。

## 2. 启动与验证顺序

### 核心（不需要外部模型）

```powershell
python -m compileall -q .
python -m pytest -q ops/test_task_ledger.py ops/test_memory_gateway.py ops/test_memory_index_recovery.py ops/test_cognitive_think_gate.py
python ops/health_check.py
python ace.py test
```

若某个测试文件在提交版本中不存在，bootstrap 只报告 `SKIP`，不得伪造通过。

### TaskPool / Worker Capsule / lease / fencing

```powershell
python -m pytest -q ops/test_task_pool.py ops/test_task_ledger.py ops/test_workspace_write_lock.py
python ace_start.py task <TASK_ID> <OWNER> 300
```

具体测试文件以仓库当前版本为准；`task_pool/` 是运行态目录，结构可重建，历史任务快照不等于源码真源。

### 视频能力域（不含 Provider）

```powershell
python -m pytest -q tests/test_production_control.py tests/test_video_kingdom_entry.py tests/test_voice_execution_steps.py
python tools/video_kingdom_entry.py --text "灾备 smoke test：只生成计划，不提交 Provider" --out temp/recovery_entry_receipt.json
```

## 3. 状态分类

- `REMOTE_CANONICAL`：源码、协议、schema、测试、恢复脚本和关键文档已经进入远程提交。
- `REMOTE_TEMPLATE`：远程有安全模板，但值必须由人/安全管理器注入。
- `REBUILDABLE`：运行态/索引/缓存可从源码和收据安全重建；不作为恢复前置。
- `OPTIONAL_EXTERNAL`：可选仓库/公开能力资产，不阻塞 ACE 核心复活。
- `SECRET_REQUIRED`：必须从私密安全来源补回，绝不公开上传。
- `LOCAL_ONLY_CRITICAL`：只在本机且无法从远程或安全来源重建；出现即 FAIL。当前基线不得有此项。

## 4. 复活判定

本基线已满足以下条件；以后任何行为性修改都必须重新满足它们：

- 两个核心仓库的关键本地修改已审阅、提交并推送（`ace_core@2ce7f9068441c0d341d8ed26cec1ea77d72cdbf8`；`ace-video-kingdom@27da48891ac778e88689fd1e33cdc058472f9b90`）；
- 远程提交可由新目录 checkout；
- 配置模板、恢复脚本、协议、schema、测试、模型能力定义和关键文档均在远程；
- 没有 `LOCAL_ONLY_CRITICAL`；
- 私密依赖全部列在 `MISSING_HUMAN_REQUIRED.md`，并有来源/变量名/补回方式；
- 隔离目录 `D:\tmp\ace_dr_final_20260930` 只使用远程 clone + 明确安全输入完成 bootstrap、基础测试、health check 和核心入口 smoke test；
- `RESTORE_TEST_RESULT.md` 记录真实命令、commit、结果与任何限制；空 checkout 尚未启动 daemon 时的 health error 不再被误判为远程缺失，当前 daemon 启动后 `errors=0`。

本文件不把“远程已经 push，应该可以恢复”当作证据；必须有可重放的恢复收据。
