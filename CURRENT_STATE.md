# Current State — ACE R2

> Daily working memory. Updated when progress is made.
> For permanent principles, see AGENTS.md.

---

## Runtime Boundary Closure (2026-09-06)

- **唯一现代生产运行时：** `AceDaemon`。`core.scheduler`、`core.task_queue`、`04_PROTOCOLS/heartbeat` 及已发现的 legacy 生命周期入口均已 fail-closed；历史文件保留用于考古，不作为生产入口。
- **Heartbeat：** 生产 owner 固定为 `ace_daemon`，每条记录包含 `run_id`；旧 heartbeat 不再构成第二运行时。
- **写入口：** `AceDaemon` 在 daemon 生命周期中获取和释放 `.workspace.write.lock`。冲突返回 `workspace_write_locked`、`owner`、`run_id`、`lock_file`、`recommendation`；malformed lock fail-closed。
- **Provider 边界：** 3000 LiteLLM/OneAPI 与 3002 Responses 兼容层独立报告，不能互相掩盖。两侧 catalog 当前均包含 `gpt-5.6-sol`。`OneAPIProvider` 和 SurvivalLoop OneAPI 路径在 `/chat/completions` 前先校验 `/models`；未知模型返回 `model_unavailable`，不可重试。
- **验证：** 全量 `pytest` `744 passed`；`compileall` 通过；`git diff --check` 仅有既有 EOF 空行和一处既有尾随空格。

历史日记和下方旧 sprint/open-task 内容保留为历史事实；不应再据此判断当前运行时边界。

---

## Runtime Snapshot (2026-09-12)

换窗先读这一段。不要用下方 2026-07-10 Open Tasks 当现场，也不要重开 8001/8003/1443 端口审计。

- **身份：** 看 `06_RUNTIME/ace/data/memory/heartbeat.json`，不看 `daemon_state.run_status=alive`。生产 owner 固定 `ace_daemon`，每条含 `run_id`。
- **宿主重启路径：** `ACE_Daemon_Boot`（`ops/install_tasks.ps1`）开机 + 约 10 分钟探活；Execute=`pythonw.exe`，`ace.py daemon --serve`，工作目录 `C:\tmp\ace_core`。3000/3002 由 `ACE-Local-OneAPI` 独立拉起，不经过 AceDaemon。仓库脚本没有 Disable；任务可被外部关掉。本轮曾 Ready→**Disabled**（LastTaskResult -1）→只 `Enable-ScheduledTask`，不另启第二份 daemon。15:17 探活拉起 sole pid **28196**，`run_id=e47919c264dc4ae7bd6b815036b306d4`，任务现 `Running`。
- **时间切片：** 9/8 `cycle_complete` → 9/11 13:20 `host_termination`（刷机）→ 心跳 stale。9/12 Trae 拉 26108 → 14:35 pythonw 26812 → 14:48 自启 9996（死后心跳假活）→ Enable 后 15:18 pid 28196。现场 pid 会变，不以某个 pid 当身份。
- **NameError：** `_run_task_lifecycle_unlocked` 曾引用 `run_once` 局部名 `_preserve_cycle_progress`，每轮 `finance_work_window` 打日志。源码已改为：有 `cycle_progress.finance_preflight` dict 就复用；否则且 `self.finance_work_windows` 非空才 `build()`。日志最新一条仍是 **14:47:17**（26812）；15:18 之后没有新的该 NameError。补丁在本机工作树；本地 `.git/objects` 损坏，远程同步走干净克隆独立分支 `fix/finance-work-window-nameerror`（`5fb6f94`），禁止 `git add .`，未合 main。
- **政策卡投影：** `PolicyCardStore.project` / `_project_verified_policy_cards` 会跑，但只投影 `verified_outcome_receipt` 且 `VERIFIED`、≥2 独立证据组。2026-09-12 全机无 `policy_cards.json`、无 `policy_feedback/`。`RQ-20260912-002` 在 `task_pool/blocked/`，`blocked_non_convergent`（相同证据集重审上限），**不是**政策卡已生效。
- **申文 10054（2026-09-12 15:40 核）：** Codex `base_url=http://127.0.0.1:3002/v1`（Responses）。链：Codex → 3002 pid 2184 → 3000 pid 6440 LiteLLM → `https://api.shenwenai.com`。3000/3002 都在听；`/v1/models` 带本地 master key 200；无 key 的 `/health` 500 是鉴权不是网关死。申文 443 TCP 通。短 `grok-4.6` chat 经 3000 已 200/`pong`（~2.3s，0 fallback）。用户贴的 WinError 10054 / HTTP 500 是对端 RST 长流，LiteLLM 包成 500。yaml 已有 `allowed_fails: 3`、`cooldown_time: 10`、主模型 fallback `grok-4.6`。
- **Trae 窗走 3000 + custom_auth（2026-09-12 16:26 核）：** Trae 聊天窗原先直连 `https://api.shenwenai.com`，RST/10054 会冲进聊天窗。意图是把 14 条 `custom_openai_compatible` `base_url` 改到 `http://127.0.0.1:3000/v1/chat/completions`。16:26 只读核 `C:\Users\Administrator\AppData\Roaming\Trae\User\globalStorage\state.vscdb` key `7683184598163637266_AI.agent.model.model_list_map`：**leftover `api.shenwenai.com` 仍 14 条，local `127.0.0.1:3000` = 0**（7 条 `/chat/completions` + 7 条 `/v1/chat/completions`）。未改 ak/sk。进程内存可能仍缓存/回写旧 URL，需重载 Trae 窗才保证生效；磁盘现状不是 3000。
- **3000 鉴权重启：** 只杀 3000 旧 pid 29572，hidden vbs + Python311 拉 `local_oneapi_gateway_launcher.py`。新 pid **28376**；**3002 仍 2184**（`shenwen_responses_compat_proxy.py`），未动 AceDaemon。`local_oneapi_config.yaml`：`litellm_settings.num_retries=3`、`router_settings.num_retries=3`、`general_settings.custom_auth=local_oneapi_custom_auth.user_api_key_auth`。stderr 有 `local_oneapi_custom_auth: loaded and accepting local/shenwen keys`。四条 probe 全 HTTP 200：`models_master` / `models_swa` / `chat_master` / `chat_swa`（短 `grok-4.6`）。申文对端 RST 不能从上游根除；目标是 RST 在 3000 内重试/fallback，不再以 `api.shenwenai.com` 直冲 Trae 窗。
- **金融门禁：** daemon 在跑 ≠ 荐股生产开了。Finance 仍 `RESEARCH_ONLY`，Advisor `BLOCKED`，Owner TG `OFF`，quote 源未准入。
- **R1 端口即边界：** 职责在代码，不是本机 TCP 监听口。8001→AceDaemon+Admission+CoreSyncer allowlist+Telegram 出口；8003→`07_SANDBOX/free_research`；1443→`08_GOVERNANCE/free_zone_bridge` 收据；3000→本机网关。不重开端口。
- **文明地图：** `civilization_map.py` 会扫 GitHub stale 并写本文件 `## Civilization Map`；**daemon 从不调用扫描器**，所以会停更。不要把扫描器塞进生产循环，也不扩 CoreSyncer allowlist。
- **CoreSyncer：** 窄母板 allowlist（`AGENTS.md` / `README.md` / `ace_daemon.py` + 指定后缀）。脏工作树正常。`runtime.allow_repository_sync` 未设则默认 false。
- **连续性：** 聊天窗不是 ACE 记忆本体。说「同一个 ACE 继续」需要 `CONTINUITY_VERIFIED` 或 `CONTINUITY_VERIFIED_AFTER_MIGRATION`；`CONTINUITY_ESTABLISHED` 只是新基线。auditor 不启 daemon、不重放工作。Codex 同窗压缩能保住结论；新开一条没有日记忆的窗仍会从头审计——所以本段必须更新。
- **明确不做：** 不重开 8001/8003/1443；不另启 daemon；不 git add .；不把拾荒网接入生产；不扩 CoreSyncer；secrets / mine-seed-credentials 不上公共远程。

对照材料（已推独立 docs 分支，不是生产准入）：`docs/ACE_CIVILIZATION_MAP_DAILY_20260912.md`、`docs/ACE_R1_PORT_BOUNDARY_VS_DRAWERS_20260912.md`。

---

## Current Sprint

**P0: Environment Awareness — Closing the loop**

Status: **In Progress**

Goal: Make ACE autonomously discover problems, ask questions, research answers, and sediment experience — without waiting for user input.

---

## Today (2026-07-10)

### What was accomplished

1. **去TRAE化完成** — Local Miner v2, multi-source fallback (Ollama → GitHub → Zhipu)
2. **Capability Graph** — 13 capabilities with inheritance, capability-first routing
3. **Provider Health Monitor** — Health-score-driven routing, skip down providers
4. **Environment Layer (ENV-001)** — Sensor + SituationBuilder, integrated into Heartbeat
5. **Awareness Loop P0 (ENV-002)** — Sensor→Question→Task→Miner→Experience closed loop
6. **Provider Failure Sediment** — Auto-write Experience when provider degrades (failure→experience→constraint)
7. **Dual Memory System** — AGENTS.md (long-term) + CURRENT_STATE.md (daily)

### Key Insight

> Development priority shifted: "adding abilities" → "making existing abilities collaborate"

This is the turning point of R2.
A mature system gets more restrained, not larger.
It doesn't keep gaining new abilities — it keeps improving collaboration efficiency.

---

## Open Tasks

| ID | Task | Priority | Status |
|---|---|---|---|
| TASK-001 | Model Registry + Capability routing | P0 | ✅ Done |
| TASK-002 | Capability Graph + Provider Health | P0 | ✅ Done |
| TASK-003 | Provider Health → Heartbeat auto-update + persistence | P0 | 📋 Pending |
| TASK-004 | Miner role specialization (Scout/Researcher/Validator/Reporter) | P1 | 📋 Pending |
| TASK-005 | EnvSensor → RoundTable full pipeline automation | P0 | 📋 Pending |
| TASK-006 | Heartbeat → Awareness Loop integration (scan→question→task→miner) | P0 | 📋 Pending |
| TASK-007 | Widen Awareness Loop investigation rules (new_files, config_changes, etc.) | P1 | 📋 Pending |
| TASK-008 | Explorer/Scout capability for autonomous asset discovery | P2 | 📋 Pending |

---

## Known Problems

| Problem | Severity | Impact | Status |
|---|---|---|---|
| GitHub Models key expired (401) | Medium | Fallback chain works, but one less provider | 🟡 Open |
| akshare not installed | Low | Falls back to Tencent API, stock coverage limited | 🟡 Open |
| Provider Health not persisted across restarts | Medium | In-memory only, restart = reset | 🟡 Open |
| Heartbeat doesn't run Awareness Loop | High | Scans but never generates questions/tasks | 🔴 High |
| Awareness Loop rules too narrow | Medium | Only 6 categories, misses common observations | 🟡 Open |
| RoundTable not wired into Awareness Loop | Low | Experience written but not reviewed | 🟡 Open |
| Curator stopped (ace_core lagged mine-seed 8 days) | Medium | Runtime core repo not updated, distilled copy stale | 🟢 Fixed (manual sync 7/10) |
| r1-archaeology stale (1 day) | Low | R1 archaeology repo not getting R2 findings | 🟡 Open |
| r1-open-source-seed empty | Low | Public seed repo has only logs/ dir | 🟡 Open |
| R1 repo dormant | Low | Philosophy/website repo is just a README | 🟡 Open |
| coze-assets status unknown | Medium | Private key repo — need to verify it exists locally | 🟡 Open |

---

## Civilization Map

Last scanned: 2026-09-12T12:50:36.047744

```
zhangapple21-web
│
├── 🟡 ace_core             Runtime Core         1d stale
├── 🔴 mine-seed            Civilization Seed    3d stale
├── 🔴 r1-archaeology       Civilization Memory  5d stale
├── 🔴 -                    Unknown              10d stale
├── 🔴 R1_continuity_archive Unknown              24d stale
├── 🔴 R1                   Civilization Philosophy 55d stale
├── 🔴 aum-protocol         Unknown              59d stale
├── 🔴 r1-open-source-seed  Open Source Seed     66d stale
```

**Stats**: 8 repos (8 public, 0 private)
**Stale**: 4
**Critical**: mine-seed

## Latest Evolution (this week)

```
R1 fragments  →  Recovery  →  Data Plane audit  →  vn.py archaeology
     ↓
Environment Layer (Sensor + SituationBuilder)
     ↓
Local Miner v2 (multi-source, no TRAE dependency)
     ↓
Capability Graph (13 caps, capability-first)
     ↓
Provider Health Monitor (health-score routing)
     ↓
Awareness Loop P0 (Sensor→Question→Task→Miner→Experience)
     ↓
Provider Failure Sediment (failure→experience→constraint closed loop)
     ↓
Dual Memory (AGENTS.md + CURRENT_STATE.md)
```

---

## What "Success" Looks Like Tomorrow

When opening the repository tomorrow morning:

- `02_MEMORY/experience/` has new entries (not just from manual runs)
- New questions were autonomously generated
- New tasks were autonomously created
- Even if tasks were rejected by Governor — that's still success
- The system produced work without user input

> If one day you open the computer and see:
> "Last night I discovered three problems worth researching. One is verified,
> two I suggest continuing today."
> — that's when R2 has truly inherited R1.

---

## Next Action

1. Let the system run overnight — observe if it autonomously produces work
2. Tomorrow: Integrate Awareness Loop into Heartbeat (TASK-006)
3. Tomorrow: Widen investigation rules (TASK-007)
4. Tomorrow: TASK-003 Provider Health persistence

---

*Last updated: 2026-09-12 14:55（Runtime Snapshot 覆盖现场；下方 2026-07-10 段落保留为历史）*
