# Continue Gate 运行时审计（2026-09-04）

## 范围

本次只审计并接入三个现有生产入口：

- `ace_daemon.py` 的周期循环与 `run_once`
- DramaAI `src/core/pipeline/video-shot.ts` 的分镜视频入口
- Infinite Canvas `web/src/pages/video/index.tsx` 与 `web/src/services/api/video.ts` 的视频工作台入口

不把 FastMovieAI、Free Zone 或未来新脚本当成已接入入口；它们仍需在自己的第一次外部动作/任务恢复前调用 `continue_gate`。

## 已确认的运行时缺口

1. ACE 原先在心跳、诊断和 Shenwen 健康调用之后才判门，门禁不能阻止这些前置动作。
2. 两个前端入口原先把“任务句柄已创建”记为成功，未等到可播放视频或本地资产落盘。
3. 前端没有持久化“动作已开始但还没有终态 receipt”的状态，刷新/崩溃后无法区分可恢复任务和盲目重试。
4. Infinite Canvas 的页面轮询恢复路径没有再次经过门禁；配置缺少 base URL 或 API key 时也可能被当作可用协议。

## 运行时修复

- ACE 在每个周期最前面和 `run_once` 入口调用 `_check_continue_gate()`；关闭时只写 handoff receipt、设置 `handoff_required` 并停止周期。
- 三个入口在门禁关闭时都写 `HANDOFF_REQUIRED` receipt；它不是成功凭证，也不会清除未完成标记。
- DramaAI/Infinite Canvas 在 provider 调用前写入 in-flight 标记；任务 ID 与日志持久化后写 `SUBMITTED`；仅成功资产或明确失败写 `SUCCEEDED`/`FAILED`。
- 所有前端 gate session 的写入都先读取最新状态，避免并发/异步回调覆盖 failure 计数。
- Infinite Canvas 的页面恢复轮询和 API 封装均执行门禁，并把凭据/端点完整性纳入 `available`。
- TypeScript 决策结果补齐 `continue_before_work.v1` 的 snake_case 字段，便于跨入口审计。

## 验证

- ACE：`ops/test_continue_gate.py` 与 `ops/test_runtime_continue_gate.py`，6 passed。
- DramaAI：`npm run typecheck` 通过。
- Infinite Canvas：`npm run typecheck` 通过。

## 保留边界

本次没有把 Free Zone 变成生产队列，也没有新增 Scheduler/Router。未来新增入口必须显式调用 `continue_gate`；仅增加文档、配置或 receipt 不算运行时接入。
