# ACE Recovery Map（灾备与一键复活基线）

> 基线日期：2026-09-30（Asia/Shanghai）
> 当前结论：`BACKUP_COMPLETE / RECOVERABLE`（核心离线复活与视频能力域 dry-run 已在独立目录验证；私密凭据、模型权重、私有媒体按人工清单补回）。

## 1. 真源与边界

- **核心真源（C 盘职责）**：`ace_core`。包含当前 ACE 认知运行时、AceDaemon、TaskPool、Worker Capsule、lease/fencing、Researcher/Validator/Guardian/Archivist、MemoryGateway/MemoryIndex、协议、schema、迁移、测试、启动与恢复入口。
- **视频能力域（D 盘职责）**：`ace-video-kingdom`。包含视频控制面、能力/模型路由、生产门禁、规则、测试和入口；不替代 `ace_core`。
- **能力与知识扩展**：`ace-capability-registry`、`ace-skill-vault`、`ace-knowledge-forge`、`ace-salvage`、`ace-structure-steward`。它们用于能力登记、Skill、知识锻造、保全和治理，不是核心启动前置。
- **可选资产**：`ace-video-assets`（公开参考资产）、`R1_continuity_archive`（历史/考古知识）。
- **私密资产**：凭据、私有媒体、CosyVoice 权重等不得进入公开 Git，见 `MISSING_HUMAN_REQUIRED.md`。
- **废弃路径**：`3000`、`3002`、legacy scheduler、legacy heartbeat 仅保留历史证据，禁止进入恢复启动链。

## 2. 新机器恢复顺序

1. 安装 Git、Python 3.11+；PowerShell 仅用于 `.ps1` 包装器。
2. 在全新空目录执行（推荐直接使用恢复编排入口）：
   - Windows：`pwsh -File recovery/restore_from_remote.ps1 -WorkspaceRoot D:\\ACE_RESTORE -WithVideo`
   - Python：`python recovery/restore_from_remote.py --workspace-root D:\\ACE_RESTORE --with-video`
3. 入口只从 GitHub clone `ace_core` canonical branch；拒绝覆盖非空目标；运行 `recovery/bootstrap.py`。
4. `bootstrap` 生成本机 `ace_config.local.json`、可重建目录、compileall、核心离线测试和 `ace.py status`；不读取旧电脑、不下载密钥、不启动 Provider。
5. 如需视频能力，入口再 clone `ace-video-kingdom/main`，运行视频测试与 Provider-free dry-run；加 `--with-optional` 可同时恢复 capability registry、skill vault、knowledge forge、salvage、structure steward、公开视频资产和 R1 continuity archive。
6. 按 `MISSING_HUMAN_REQUIRED.md` 从安全来源补回凭据、模型权重和获授权媒体；未补回时只能使用离线能力，不得宣称外部 Provider 已恢复。
7. 运维授权后再启动当前 `ace.py daemon --serve ...` 并运行 `ops/health_check.py --json`；空 checkout 未启动 daemon 时的 heartbeat error 是预期门槛，不是缺失源码。

## 3. 当前验证基线

- `ace_core` canonical branch：`core/daemon-lifecycle-resilience-20260912`
- `ace_core` 当前远程 HEAD：`14f48ff4631ee6431c5127aece4f46acb3edb60d`
- `ace_core` 行为验证基线：`2ce7f9068441c0d341d8ed26cec1ea77d72cdbf8`
- `ace-video-kingdom/main`：`27da48891ac778e88689fd1e33cdc058472f9b90`
- 最新独立演练目录：`D:\\tmp\\ace_dr_final_20260930_r3`（历史收据）；最终入口演练以 `ACE_REMOTE_RESTORE_RECEIPT.json` 为准。

## 4. 验收标准

必须同时满足：远程 ref 可 checkout；bootstrap/compileall/离线测试通过；TaskPool/lease/fencing 演练通过；当前 AceDaemon 启动后 health `errors=0`；视频 dry-run 完成且 `provider_submission=NOT_PERFORMED`；没有 `LOCAL_ONLY_CRITICAL`；人工依赖有来源、变量名和补回方式。

`task_pool/`、MemoryIndex、heartbeat、缓存、日志和渲染输出是可重建或需人工恢复的运行态，不是源码真源。任何关键行为修改都必须重新演练并更新收据。
