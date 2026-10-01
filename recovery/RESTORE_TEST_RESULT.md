# Restore Test Result

基线日期：2026-09-30
状态：`RESTORE_ENTRY_AVAILABLE / REMOTE_REVALIDATION_REQUIRED`。仓库内可复核入口和离线测试，不据此宣称整机备份完整或当前远程恢复成功。

## 当前入口可复核范围

`recovery/restore_from_remote.py --workspace-root <空目录> [--with-video] [--with-optional]`：

- 每个 clone 前执行 `git ls-remote --heads URL REF`，解析指定分支的唯一 HEAD；clone 后记录分支和 HEAD，HEAD 不一致则 FAIL 并阻断后续步骤。
- 每个 clone step 保留命令输出及 `requested_ref`、`remote_head`、`checked_out_branch`、`checked_out_head`、`ref_match`。成功收据为目标目录的 `ACE_REMOTE_RESTORE_RECEIPT.json`。
- 失败时将本次工作区与失败收据保留在目标父目录的 `<目标名>_failed_*` 目录，不覆盖原有资产；原目标可重试。
- 核心步骤仅调用 `recovery/bootstrap.py`：重建目录/配置模板、compileall、可用时运行列出的有限 pytest、health/status 检查。bootstrap 的 WARN/SKIP 不会自动阻断，必须检查其嵌套报告；编排器 PASS 不等于 daemon health 通过。
- `--with-video` 在未指定 `--skip-tests` 时运行三份视频离线测试及入口 dry-run；`--with-optional` 只 clone 列出的可选仓库。`--skip-tests` 不证明任何测试通过。
- 当前入口**未执行** TaskPool/Worker/lease/fencing 60 项专项、跨进程 death drill 或 daemon 启动；不得将这些项目记为当前入口的 PASS。
- 不读取旧工作区、不下载凭据、不启动 Provider 或废弃端口。远程可变分支若在查询与 clone 间变化，校验失败，需要重新恢复，不能静默接受。

## 历史外部演练（非当前入口自动证据）

历史报告引用 `D:\\tmp\\ace_dr_final_final4\\ACE_REMOTE_RESTORE_RECEIPT.json`，记录核心演练 HEAD `85f7575fe1c8b78f58e85623535ce1bd9e0db3ae`、视频 HEAD `27da48891ac778e88689fd1e33cdc058472f9b90`，以及 bootstrap `34 passed`、视频测试 `36 passed`、专项 `60 passed`、death drill `HALF_DONE → PASS`、daemon 启动和 health `errors=0`。

这些是历史外部报告中的陈述；该收据及专项/daemon 的完整独立命令证据不在本仓库中，本次未重新验证。尤其专项、death drill、daemon 启动不是当前恢复入口的步骤，不能由上述入口复现其结论，也不能用历史计数替代新运行的实际输出。

## 冷启动与人工恢复限制

冷 checkout 未启动 daemon 时的 health 报告不能当作已运行 daemon 的健康证据；当前入口不授权或执行 daemon 启动。

凭据、Provider、CosyVoice 权重、私有媒体和运行态历史不进入公开 Git；人工补回方式见 `MISSING_HUMAN_REQUIRED.md`。缺少这些输入时，不宣称外部能力或整机恢复完整。
