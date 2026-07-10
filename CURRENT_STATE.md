# Current State — ACE R2

> Daily working memory. Updated when progress is made.
> For permanent principles, see AGENTS.md.

---

## Current Sprint

**P0: Environment Awareness — Closing the loop**

Status: **In Progress**

Goal: Make ACE autonomously discover problems, ask questions, research answers, and sediment experience — without waiting for user input.

---

## Today (2026-07-10)

### What was accomplished

1. **去TRAE化完成** — Local Miner v2, multi-source fallback (Ollama → GitHub → Zhipu → OpenRouter)
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
| OpenRouter key expired (401) | Medium | Fallback chain works, but one less provider | 🟡 Open |
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

## Civilization Map (7 repos)

```
zhangapple21-web
│
├── 🏠 mine-seed              Active     9.3MB   R2 HQ (今天的主战场)
├── ⚡ ace_core               Active     1.5MB   Runtime 精选 (刚从 8 天停更恢复)
├── 🏛️ r1-archaeology          Warming    310KB   考古档案馆 (昨天更新过)
├── 🌱 r1-open-source-seed    Stale       32KB   开源种子 (几乎空的)
├── 📜 R1                     Dormant      0KB   文明思想/官网 (空壳)
├── 🧪 -                      Dormant      0KB   测试仓库
└── 🔑 coze-assets            PRIVATE      ?     文明钥匙 (密钥，绝不公开)
```

**Cross-repo observation:** Each repo is an organ, not a silo.
When one is stale, it's a civilization health problem, not just "inactive".

---

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

*Last updated: 2026-07-10 20:30*
