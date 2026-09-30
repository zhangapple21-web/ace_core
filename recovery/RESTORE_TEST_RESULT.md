# Restore Test Result

基线日期：2026-09-30
状态：`BACKUP_COMPLETE / RECOVERABLE`（核心离线链、视频 Provider-free 链和非 C/D 盘符路径演练；外部服务/私有资产仍按人工清单）。


## 便携路径复核（提交 `17b90ebb717ee2e84b1dcf7a8f5c065a9c6d573d`）

- `portable_paths.ROOTS` 单一解析层：PASS。
- 关键执行链绝对路径审计：PASS；`recovery/path_audit.py` 无 findings。
- 非 C/D 盘符模拟（`Y:` subst 隔离根）：PASS；仅从远程 clone、bootstrap、核心测试、视频 clone/test/dry-run 均通过。
- 核心专项回归：PASS；`63 passed`。

## 最终独立演练（仅从远程真源）

演练编排器先从 GitHub clone `ace_core` canonical branch，再由该远程 checkout 执行 `recovery/restore_from_remote.py --workspace-root D:\\tmp\\ace_dr_final_final4 --with-video --with-optional`。编排器拒绝覆盖非空目录，不读取当前工作区、不下载凭据、不启动 Provider 或废弃端口。

最终收据：`D:\\tmp\\ace_dr_final_final4\\ACE_REMOTE_RESTORE_RECEIPT.json`

| 验证项 | 结果 |
|---|---|
| `ace_core` clone | PASS；远程分支 checkout，便携路径演练核心 HEAD：`17b90ebb717ee2e84b1dcf7a8f5c065a9c6d573d`；视频 HEAD：`27da48891ac778e88689fd1e33cdc058472f9b90` |
| `bootstrap.py` | PASS；compileall PASS；bootstrap pytest `34 passed`；`ace.py status` PASS |
| TaskPool/Worker/lease/fencing 专项 | PASS；`60 passed` |
| Worker Capsule 跨进程 death drill | PASS；`first=HALF_DONE`，等待 lease 过期后 `resume=PASS`，旧 fencing 清除，最终 `review` |
| 当前 AceDaemon | PASS；直接运行 `ace.py daemon --serve --interval 1 --max-iter 8 --dry-run --force` 正常退出 `0` |
| `ops/health_check.py --json` | PASS 门槛；daemon 已授权启动时 `errors=0`（`warnings=2` 仅为空知识/归档状态，健康命令本身以 warning exit `1` 退出） |
| `ace-video-kingdom` clone | PASS；`main` |
| 视频离线测试 | PASS；`36 passed` |
| 视频入口 dry-run | PASS；`COMPLETED`，`provider_submission=NOT_PERFORMED` |
| 3000/3002、legacy scheduler/heartbeat | 未由恢复链启动；未成为恢复依赖 |

当前机器的 `127.0.0.1:3000` 若存在，是已有的 `local_oneapi_gateway_launcher.py` 外部进程，不是本恢复入口启动的 ACE 旧路径；恢复脚本未触碰该进程。

## 冷启动限制

冷 checkout 未启动 daemon 时，health 会报告 heartbeat error；这是未授权启动的预期门槛，不是远程缺失。按运维授权启动当前 `AceDaemon` 后再以 `errors=0` 验收。

凭据、Provider、CosyVoice 权重、私有媒体和运行态历史不进入公开 Git；来源与人工补回方式见 `MISSING_HUMAN_REQUIRED.md`。没有这些输入时，核心离线能力仍可复活，外部能力保持受限。
