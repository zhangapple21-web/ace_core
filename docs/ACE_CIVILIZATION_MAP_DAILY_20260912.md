# ACE 文明地图日报 — 2026-09-12

> 最小刷新。只跑现成 `core/civilization_map.py --scan --report`。
> 不覆盖 `08_ARCHAEOLOGY/CIVILIZATION_MAP.md` / `09_KNOWLEDGE/CIVILIZATION_MAP.md`。
> 不跑 `--auto`，不改 daemon，不扩 CoreSyncer。
> 本文件放 `docs/`，是已分类可提交材料；`CURRENT_STATE.md` / `02_MEMORY` / `research/` 仍故意不进母板 allowlist。

## 结论

停更判断属实。扫描器在，daemon 从不调用；CoreSyncer 最后一次 PUSHED 是 2026-09-01；`CURRENT_STATE.md` 地图段在刷新前仍是 2026-07-10 手工快照。

本次只做一件事：把 GitHub 组织公开仓的新鲜度写回地图段，并留下这份日期文件。

## 今日 GitHub 公开仓

未认证 API，看不到 private（`coze-assets` 缺席，private=0）。

| 仓 | 角色 | 上次远程 push | 停更 | 判定 |
|---|---|---|---|---|
| ace_core | Runtime Core | 2026-09-11 | 1d | Warning（阈值 2d，未超） |
| mine-seed | Civilization Seed | 2026-09-08 | 3d | Critical（阈值 1d） |
| r1-archaeology | Civilization Memory | 2026-09-06 | 5d | Critical 标签，但未超 7d 阈值，不计入 stale_count |
| - | Unknown | 2026-09-01 | 10d | Dormant，未超 30d |
| R1_continuity_archive | Unknown | 2026-08-19 | 24d | Dormant，未超 30d |
| R1 | Civilization Philosophy | 2026-07-19 | 55d | Abandoned |
| aum-protocol | Unknown | 2026-07-14 | 59d | Abandoned |
| r1-open-source-seed | Open Source Seed | 2026-07-08 | 66d | Abandoned |

Stale（相对各自阈值）= 4：`mine-seed`、`R1`、`aum-protocol`、`r1-open-source-seed`。
Critical stale = `mine-seed`。

## 本地记忆仓新鲜度（未改这些仓的设计稿）

- ace_core runtime `memory_index.json`：2026-09-08，4225 条。运行时还在写，但不是文明地图日报。
- ace_core `02_MEMORY/environment`：停在 2026-08-31。
- mine-seed `civilization_daily_*.md`：最后一份 2026-08-19。
- CoreSyncer：2026-09-01 后未 PUSHED；`CURRENT_STATE.md`、`02_MEMORY`、`research/` 本就不在母板 allowlist。
- 扫描器顺带沉淀了 4 条 `02_MEMORY/experience/exp_repo_stale_*_20260912T125036.json`。这是 `--scan` 原有行为，不是新逻辑。

## 本次改动

1. 更新 `CURRENT_STATE.md` 的 `## Civilization Map` 段（顶部 2026-09-06 Runtime Boundary 未动）。本地工作记忆，不自动推远程。
2. 新增 `research/ACE_CIVILIZATION_MAP_DAILY_20260912.md` 与 `research/remote_civilization_map_20260912.json`。
3. 本文件作为已分类副本，供远程同步。

## 故意没做

- 不把扫描器挂进 `ace_daemon` 生产循环。
- 不扩 CoreSyncer allowlist。
- 不 `git add .`，不修坏掉的 `ace_core/.git/objects`。
- 不覆盖复活计划 `NEW_COMPUTER_RESURRECTION.md`（仍是 2026-07-10）。
- 不把拾荒网/荐股/老师审阅拉进来。
