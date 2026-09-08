# ACE 收口复核 — 2026-09-06

## 结论

本轮能在本地安全收口的测试边界已完成：生产 `TaskPool` 继续强制 admission，旧测试迁移到显式 `FixtureTaskPool`；没有放宽生产门槛、没有提交、没有推送、没有发送外部消息。

## 已验证事实

- 全量回归：`723 passed in 146.38s`。
- 针对性回归：`63 passed in 32.15s`，覆盖 execution discipline、model pool mainline、task admission、runtime authority、legacy CLI。
- 独立 ACE start 验收：`PASS`；仅使用临时 `TaskPool`，checker 未产生 runtime mutation，`checkout_wide_claim=NOT_MADE`。
- GitHub API 只读：仓库 `zhangapple21-web/coze-assets` 为 private；当前认证主体具备 `admin/push/pull`。`/rulesets` 与 `/branches/main/protection` 均返回 HTTP 403，原因是 GitHub 计划限制（需 Pro 或公开仓库）；未改变仓库可见性。
- GitHub 凭据：未在环境变量、常见明文文件或输出中暴露；Windows Git Credential Manager 可完成只读 Git/API 认证。
- 本机端口：`3000/health/liveliness=200`、`3000/v1/models=200`，`3000/health` 在 4 秒内超时；`3002/healthz=200`、`3002/v1/models=200`；`3001` 未监听。
- 当前 ACE daemon 进程、`memory/daemon_state.json`、`memory/heartbeat.json` 与 `.daemon.lock` 均未发现，因此旧日报中的 daemon 存活结论不能沿用。

## 本轮改动范围

- `ops/test_execution_discipline.py`：改用测试专用 `FixtureTaskPool`。
- `ops/test_model_pool_mainline.py`：测试 daemon 使用 `FixtureTaskPool`，成本汇总测试补齐测试边界。
- `ops/run_ace_start_acceptance.py`：临时验收使用 `FixtureTaskPool`。

这些文件与工作区其他大量用户改动保持分离，未执行清理或重置。

## 仍然阻塞 / 不作猜测

1. GitHub 规则集/分支保护：当前计划 HTTP 403，不能用 API 强行开启；需升级计划、改为公开仓库，或由用户在 GitHub 侧处理。
2. ACE daemon 未运行：本轮不擅自启动常驻进程；如需恢复，应另行做明确的启动与健康验收。
3. 3000 `/health` 超时的根因尚未定位；不影响已验证的 3002 Codex 路径，但仍是独立路由风险。
4. 工作区仍有大量未提交改动；本轮不做大范围整理、提交或推送。

## 收口状态

`LOCAL_TEST_BOUNDARY_CLOSED / API_LIMIT_CONFIRMED / RUNTIME_DAEMON_NOT_RUNNING / NO_DEPLOYMENT / NO_EXTERNAL_SEND`
