# Restore Test Result

基线日期：2026-09-30
状态：`BACKUP_COMPLETE / RECOVERABLE`（仅针对核心离线链和视频 Provider-free 链；外部服务/私有资产仍按人工清单）。

## 已验证的独立演练

历史 r3 演练目录：`D:\\tmp\\ace_dr_final_20260930_r3`。该目录由远程 clone 得到 `ace_core@14f48ff4631ee6431c5127aece4f46acb3edb60d` 与 `ace-video-kingdom@27da48891ac778e88689fd1e33cdc058472f9b90`，没有读取原工作区源码、缓存、运行态或密钥。

已完成并记录：

- `recovery/bootstrap.py`：compileall PASS；bootstrap pytest `34 passed`；`ace.py status` PASS。
- 核心专项：TaskLedger、Worker Capsule、CLI、workspace lock、admission 等 `71 passed`。
- Worker Capsule death drill：第一次 `HALF_DONE`；lease 过期后接管 `PASS`；旧 fencing token 不能继续写；最终进入 `review`。
- 当前正式入口 `ace.py daemon --serve --interval 1 --max-iter 8 --dry-run --force` 启动后，`ops/health_check.py --json` 达到 `errors=0`，进程归属与 heartbeat PASS，daemon exit `0`。冷 checkout 未启动 daemon 时 heartbeat error 是预期门槛。
- 视频能力测试 `36 passed`；`tools/video_kingdom_entry.py` dry-run 返回 `COMPLETED` 且 `provider_submission=NOT_PERFORMED`。
- 全程未启动 `3000/3002`，未恢复 legacy scheduler/heartbeat。

## 以远程恢复入口为最终证据

提交并推送本文件后，在全新空目录运行：

```powershell
py -3 recovery/restore_from_remote.py --workspace-root D:\\tmp\\ace_dr_final_final --with-video
```

该入口只允许空目录，clone 明确 canonical refs，运行核心 bootstrap、视频离线测试与 dry-run，并写出 `ACE_REMOTE_RESTORE_RECEIPT.json`。收据中的 `status=PASS` 才是最终可重放证据；若失败不得宣布可恢复。

## 限制

凭据、Provider、CosyVoice 权重、私有媒体和运行态历史不进入公开 Git；它们的来源和人工补回方式已在 `MISSING_HUMAN_REQUIRED.md` 列明。没有这些输入时，核心离线能力仍可复活，但外部能力保持受限。
