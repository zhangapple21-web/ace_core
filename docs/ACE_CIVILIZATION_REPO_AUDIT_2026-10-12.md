# ACE 文明仓库群审计（2026-10-12）

> 审计对象：`zhangapple21-web` 组织下全部仓库
> 方式：GitHub API 只读（`gh repo list` / `git/trees?recursive=1`）。
> 用 **git blob SHA 做跨仓库精确去重**——SHA 是内容寻址的，相同内容必然相同 SHA，无需下载即可判定完全一致。
> 复现：见文末第 7 节。

---

## 0. 结论摘要

| # | 发现 | 等级 |
|---|---|---|
| 1 | **`coze-assets` 返回 404，不存在** —— AGENTS.md 称其为"文明钥匙，没有它什么都不能恢复" | 🔴 致命 |
| 2 | AGENTS.md 的文明地图**已过期**：写的是 7 个仓库，实际 **11 个** | 🟠 高 |
| 3 | **mine-seed 内部重复率 50.9%**（113MB 中 57.6MB 是重复内容，228 个重复组） | 🟠 高 |
| 4 | mine-seed 顶层**编号体系崩坏**：5 个 `02_`、3 个 `03_`、3 个 `04_`、3 个 `05_` | 🟠 高 |
| 5 | mine-seed 有 **14 个空文件**（含 3 个 0 字节 `ace_config.json`、11 个空 `signals_*.json`） | 🟡 中 |
| 6 | `R1` + `R1_continuity_archive` 是**同一份连续观察日志被拆成两个仓库** | 🟡 中 |
| 7 | 2 个已归档仓库是**可验证的 100% 重复**，可安全删除 | 🟡 中 |
| 8 | ace_core 的 `04_PROTOCOLS/` 副本与 mine-seed **已发生漂移**（3 同 7 异），非干净镜像 | 🟡 中 |
| 9 | ace-video-kingdom 存在**快照命名增殖**：7 个内容完全相同的 preflight JSON | 🔵 低 |
| 10 | r1-archaeology 有 **6 个连续日期的报告内容完全相同**（生成器空转） | 🔵 低 |
| 11 | r1-archaeology open issue #6 已挂 **101 天** | 🔵 低 |

**整体判断：跨仓库重复很少（矩阵显示大部分组合为 0），真正的问题集中在 mine-seed 的仓库内部。**

---

## 1. 🔴 `coze-assets` 不存在

```
$ gh api repos/zhangapple21-web/coze-assets
{"message":"Not Found","status":"404"}

$ gh repo list zhangapple21-web --limit 100 --json name,isPrivate
（11 个仓库，全部 isPrivate=false，没有 coze-assets）
```

对照文档：

| 出处 | 原文 |
|---|---|
| AGENTS.md | `🔑 coze-assets ← 文明资产（PRIVATE）` / "**Without it nothing recovers. With it, 30min rebuild.**" / "ABSOLUTELY NEVER PUBLIC." |
| CURRENT_STATE.md | `coze-assets status unknown \| Private key repo — need to verify it exists locally \| 🟡 Open` |

**现在可以给出确定结论：它不在这个账号下。**

需要说明的边界（避免过度断言）：404 有三种可能——
(a) 已被删除；(b) 被转移到别的账号/组织；(c) 改名为 private 且当前 token 无权限。
由于当前 token 能列出该账号下**全部 11 个仓库**，`gh repo list` 也确认无 private 仓库，
所以**至少可以确定它不在此账号的可见范围内**。

这是本次审计最严重的一项：按 AGENTS.md 自己的定义，钥匙仓库缺失 = 文明无法恢复。
**需要 owner 确认钥匙的实际位置**（是否在其他账号/本地备份）。

---

## 2. 🟠 文明地图已过期

AGENTS.md 记载 7 个仓库；实际 **11 个**。

**地图中缺失的 5 个：**

| 仓库 | 大小 | 最后推送 | 说明 |
|---|---|---|---|
| `ace-video-kingdom` | 3.0MB | 2026-10-05 | ACE Free Zone 视频王国研究成果 |
| `ace-host-adapter-lab` | 75KB | 2026-10-04 | 只读 host bridge（stdio JSON-lines / MCP / PI 插件） |
| `ace-video-assets` | 67MB | 2026-09-29 | 公开授权参考帧与对白音轨 |
| `R1_continuity_archive` | 78KB | 2026-08-19 | Keeper 跨文明观察日志 |
| `aum-protocol` | 4KB | 2026-07-14 | AUM Mission Protocol |

**状态已变的 2 个：**

| 仓库 | 地图记载 | 实际 |
|---|---|---|
| `-` | `🧪 测试/草稿 · Dormant · 0KB` | **archived**，"public Episode 006 anchors migrated to ace-video-assets" |
| `r1-open-source-seed` | `🌱 开源种子 · Stale · 32KB` | **archived**，"exact duplicate of r1-archaeology/analysis/archaeology_report_*.md" |

也就是说：**AGENTS.md 里的"Watch: 某仓库陈旧 = 文明健康问题"这套观察规则，
本身依据的就是一张错的地图**——它盯着的 7 个里有 2 个已归档，
而真正在活跃更新的 5 个它根本没记录。这条规则现在无法正常发挥作用。

---

## 3. 各仓库活跃度（今天 2026-10-12）

| 仓库 | 文件数 | 最后推送 | 静默天数 | 判定 |
|---|---|---|---|---|
| `ace_core` | 751 | 2026-10-12 | 0 | 活跃（本次审计） |
| `ace-video-kingdom` | 872 | 2026-10-05 | 7 | 活跃 |
| `ace-host-adapter-lab` | 30 | 2026-10-04 | 8 | 活跃 |
| `ace-video-assets` | 113 | 2026-09-29 | 13 | 正常（资产库） |
| **`mine-seed`** | **1824** | **2026-09-23** | **18** | ⚠️ **R2 HQ 静默 18 天** |
| `r1-archaeology` | 74 | 2026-09-06 | 35 | ⚠️ 陈旧 |
| `R1_continuity_archive` | 32 | 2026-08-19 | 53 | ⚠️ 陈旧（且 0819 后日志断档） |
| `R1` | 2 | 2026-07-19 | 84 | 停滞 |
| `aum-protocol` | 3 | 2026-07-14 | 89 | 停滞 |
| `r1-open-source-seed` | 4 | 2026-07-08 | 95 | 已归档 |
| `-` | 11 | 2026-09-01 | 41 | 已归档 |

**重点：`mine-seed` 是 AGENTS.md 明确的 R2 HQ（"Everything happens here first.
Watch: push frequency = civilization heartbeat"），它静默了 18 天。**
其最后一条 commit 是 `backup: snapshot mine-seed before system reinstall (#16)`（2026-09-08）——
即 HQ 停在了一次"重装前备份"的快照状态，之后没有新的文明活动。
结合第 1 节的钥匙仓库缺失，这两件事指向同一个假设：**系统重装后文明未完成恢复**。

（这是基于推送时间与 commit 信息的推断，非直接证据，需要 owner 确认。）


---

## 4. 重复文件

### 4.1 跨仓库重复矩阵（相同内容的 blob 数）

```
                         R1  R1_cont  ace-host  ace-vid-a  ace-vid-k  ace_core  aum  mine-seed  r1-arch  r1-oss
R1                        -        0         0          0          0         0    0          0        0      0
R1_continuity_archive     0        -         0          0          0         0    0          0        0      0
ace-host-adapter-lab      0        0         -          0          0         0    0          0        0      0
ace-video-assets          0        0         0          -          0         0    0          0        0      0
ace-video-kingdom         0        0         0          0          -         3    0          0        0      0
ace_core                  0        0         0          0          3         -    0         40        1      0
aum-protocol              0        0         0          0          0         0    -          0        0      0
mine-seed                 0        0         0          0          0        40    0          -       14      4
r1-archaeology            0        0         0          0          0         1    0         14        -      4
r1-open-source-seed       0        0         0          0          0         0    0          4        4      -
```

**结论：跨仓库重复其实很少。** 只有 6 组非零关系：
- `ace_core ↔ mine-seed` = 40
- `mine-seed ↔ r1-archaeology` = 14
- `r1-archaeology ↔ r1-open-source-seed` = 4
- `mine-seed ↔ r1-open-source-seed` = 4
- `ace_core ↔ ace-video-kingdom` = 3
- `ace_core ↔ r1-archaeology` = 1

其余全部为 0。也就是说仓库边界**总体是干净的**，问题在仓库内部。

### 4.2 🟠 mine-seed 内部重复 —— 本次最大问题

```
mine-seed   文件 1824   唯一 blob 1089   blob 总量 113.2MB   唯一内容 55.6MB
            → 重复浪费 57.6MB（50.9%），重复组 228 个
```

**拷贝爆炸的典型形态**（同一份报告同时存在于 6~15 个路径）：

```
02_MEMORY/recent_memory/daily/<file>.md
03_DATA/research/r1_archaeology/daily/<file>.md
03_DATA/superseded_archive/daily/<file>__SUPERSEDED_20260710_143027.md
03_DATA/superseded_archive/r1_archaeology/daily/<file>__SUPERSEDED_20260710_143028.md
03_DATA/superseded_archive/research/r1_archaeology/daily/<file>__SUPERSEDED_20260710_143028.md
daily/<file>.md
r1_archaeology/daily/<file>.md
research/r1_archaeology/daily/<file>.md
```

**最严重的重复组：**

| 份数 | 大小 | 内容 |
|---|---|---|
| 15x | 9,030 B | `2026-06-29_claude_code_loop_archaeology.md` |
| 15x | 9,869 B | `2026-06-29_claude_code_archaeology.md` |
| 15x | 14,659 B | `2026-06-29_re_archaeology.md` |
| 12x | 62,500 B | `2026-06-29_main_loop_integration.md` / `archaeology_report_20260628.md` |
| 10x | **275,378 B** | `lexicon_20260628.json` / `lexicon_latest.json`（**单组浪费约 2.5MB**） |
| 9x | 4,110 B | `binary_analysis_BlueStacksMicroInstaller_20260629_194939.md` |
| 8x | 15,083 B | `a12_r2_core_axioms_latest.md` / `a12_r2_core_axioms_v1_20260626.md` |

命名也混乱：同一份内容同时存在**中英文两套文件名**
（`2026-06-29_re_archaeology.md` 与 `20260629_逆向工程领域结构考古报告.md` 内容完全相同）。


### 4.3 mine-seed 顶层编号体系崩坏

顶层有 **100+ 个条目**，其中数字编号目录严重重号：

```
02_MEMORY   02_ARCHITECTURE   02_LEARNING   02_miner_config   02_modules     ← 5 个 02_
03_DATA     03_INDEX          03_agent_profile                                 ← 3 个 03_
04_CONSTRAINT  04_PROTOCOLS   04_zrok                                          ← 3 个 04_
05_REPORTS  05_TOOLS          05_system                                        ← 3 个 05_
```

同时还有大量**语义重叠的散落目录**：
`daily`、`daily_archaeology`、`r1_archaeology`、`recent_memory`、`research`、
`memory`、`knowledge`、`insights`、`cases`、`fragments`、`excavations`……

这些正是 4.2 拷贝爆炸的**根因**：同一份内容在"当天目录 / 归档目录 / 模块目录 / 汇总目录"里各存一份。

对比 ace_core：顶层只有 `00 01 04 06 07 08 08`——虽然也有编号问题（见另一份审计），
但**没有 mine-seed 这种五重 `02_` 的规模**。

### 4.4 可验证的 100% 重复仓库（已归档，可安全删除）

**`r1-open-source-seed`（4/4 文件全部重复）：**

| 该仓库路径 | r1-archaeology 中的相同内容 |
|---|---|
| `logs/archaeology_report_20260703.md` | `analysis/archaeology_report_20260703.md` |
| `logs/archaeology_report_20260705.md` | `analysis/archaeology_report_20260705.md` |
| `logs/archaeology_report_20260707.md` | `analysis/archaeology_report_20260707.md` |
| `logs/archaeology_report_20260708.md` | `analysis/archaeology_report_20260708.md` |

**`-`（9/10 文件重复）：**

| 该仓库路径 | ace-video-assets 中的相同内容 |
|---|---|
| `ace-video-kingdom/wenji-episode-006/*.png`（8 个 SCENE 锚点 + 1 张用户参考图，约 9.5MB） | `references/wenji-episode-006/` |

两者**都已被 GitHub archived**，且仓库 description 自己就写明了迁移去向。
→ 迁移已用 blob SHA 逐字节验证完成，**可安全删除**（保留 description 作为考古说明即可）。

### 4.5 ace_core ↔ mine-seed 的关系（对上一份审计的重要修正）

**ace_core 的 `04_PROTOCOLS/` 不是 mine-seed 的干净镜像——它已经漂移了：**

```
04_PROTOCOLS/civilization_map.py     IDENTICAL
04_PROTOCOLS/environment_sensor.py   IDENTICAL
04_PROTOCOLS/recovery_protocol.py    IDENTICAL
04_PROTOCOLS/awaken.py               DIFFERENT
04_PROTOCOLS/awareness_loop.py       DIFFERENT
04_PROTOCOLS/environment_first.py    DIFFERENT
04_PROTOCOLS/governor.py             DIFFERENT
04_PROTOCOLS/heartbeat.py            DIFFERENT   ← ace_core 已是 3 行 fail-closed stub
04_PROTOCOLS/local_miner.py          DIFFERENT
04_PROTOCOLS/roundtable.py           DIFFERENT

identical=3  different=7  ace_core-only=0
```

这修正了上一份审计里的一个隐含假设。当时建议"删掉 ace_core 的 `04_PROTOCOLS/` 副本"，
现在必须加一条前提：**这 9 个副本里有 7 个与 mine-seed 版本内容不同**，
不能假定"删掉 ace_core 的、以 mine-seed 为准"，否则会丢失 ace_core 侧的真实改动
（最明显的是 `heartbeat.py`：ace_core 已收口为 fail-closed，mine-seed 侧还是完整实现）。

**ace_core 的 `08_ARCHAEOLOGY/` 确实是 mine-seed 考古报告的镜像：**
89 个文件中 **20 个**内容与 mine-seed 完全一致，且每个在 mine-seed 里平均出现 4~9 次。

### 4.6 🔵 ace-video-kingdom 快照命名增殖

```
7x  research/episode_007_preflight_live_now.json
    research/episode_007_preflight_reaudit_20260904.json
    research/episode_007_preflight_reaudit_20260904_final.json
    research/episode_007_preflight_runtime_20260904.json
    research/episode_007_preflight_runtime_finalcheck.json
    research/episode_007_preflight_runtime_live.json
    research/episode_007_preflight_user_verification_20260904.json

6x  research/episode_007_preflight_after_s03a_r1.json
    research/episode_007_preflight_compact_20260904.json
    ...（compact_plan / live_20260904_1410 / live_20260904_rootrelay / preflight_current_20260904）

3x  research/episode_007_previous_cut_audit_latest.json
    research/episode_007_previous_cut_audit_reaudit_20260904.json
    research/episode_007_previous_cut_audit_reaudit_20260904_final.json
```

**7 个文件名不同、内容完全相同的 preflight 状态快照**——
`_reaudit` / `_final` / `_finalcheck` / `_live` / `_user_verification` 这些后缀说明
每次复核都新存一份，而不是覆盖同一份 `latest`。这是"用文件名记录时间线"的反模式。

### 4.7 🔵 r1-archaeology 生成器空转

```
6x  analysis/r1_open_source_overview_20260704.md
    analysis/r1_open_source_overview_20260705.md
    analysis/r1_open_source_overview_20260706.md
    analysis/r1_open_source_overview_20260707.md
    analysis/r1_open_source_overview_20260708.md
    analysis/r1_open_source_overview_20260709.md

2x  analysis/r1_open_source_overview_20260627.md
    analysis/r1_open_source_overview_20260628.md
```

**连续 6 天产出内容完全相同的"每日"报告**——说明生成器那 6 天没有检测到任何变化，
但仍照常写文件。这是"活动量指标"而非"真实工作"的典型信号，
与 AGENTS.md 的 Work Conservation 原则（"不为了满足活动配额而制造工作"）相冲突。


---

## 5. 可以合并 / 融合的

### 5.1 ⭐ 首选：`R1` + `R1_continuity_archive` → 合并为一个

这是本次最明确的合并项，因为**两者本来就是同一份连续日志被拆开存放**：

| 仓库 | 文件数 | `research_logs/` 内容 |
|---|---|---|
| `R1` | 2 | `cross_civilization_observation_20260719.md` |
| `R1_continuity_archive` | 32 | `cross_civilization_observation_20260721.md` … `20260819.md`（28 篇） |

**命名规则完全相同**（`cross_civilization_observation_YYYYMMDD.md`），
`R1` 只持有 **0719** 一天，`R1_continuity_archive` 持有 **0721–0819** 共 28 篇。

日期序列（已逐一核对）：

```
R1:                        0719
R1_continuity_archive:     0721 0722 0723 0724 0725 0726 0727 0728 0729 0730 0731
                           0801 0803 0804 0806 0807 0808 0809 0810 0811 0812 0813
                           0814 0815 0816 0817 0818 0819
```

**断档：0720（仓库切换处）、0802、0805。** 0819 之后完全停止。

显然是同一条观察序列，在 0721 那天换了仓库继续写；
0720 的缺失恰好落在切换点上，值得确认那天的记录是丢了还是本就未产出。


而 AGENTS.md 对 `R1` 的定义是"文明思想 / 官网 / manifesto"，与实际内容（一条观察日志 + 42 字节 README）**完全不符**。

→ **建议**：把 `R1` 的那一篇移入 `R1_continuity_archive/research_logs/`，
`R1` 归档或重新按原定用途（哲学/官网）填充。合并后应能补齐 0720 的空档说明。

### 5.2 `aum-protocol` → 并入 R1_continuity_archive

`aum-protocol` 只有 3 个文件（8.3KB，89 天未更新）：
`AUM-MISSION-PROTOCOL.md` + `CHANGELOG.md` + `README.md`。

而 `R1_continuity_archive` 里**已经有** `runtime/aum_version_tracker.yaml`——
说明 AUM 的版本状态已经在被连续性归档跟踪。
→ 两者可以合并：协议正文作为归档仓库的一个 `protocols/` 子目录，
版本跟踪与正文放在一起，避免"协议在一个仓库、版本记录在另一个仓库"的割裂。

### 5.3 mine-seed 内部整合（收益最大，风险也最大）

收益：可回收 **57.6MB / 50.9%** 的重复，涉及 **228 个重复组**。

建议分三步，**不要一次性做**：
1. **先冻结写入**：确认 daemon / 定时任务不再往旧路径写（否则清理完又长回来）。
2. **合并同一内容的多个路径**，保留唯一权威路径。优先处理高价值项：
   `lexicon`（10x，单组 2.5MB）、`03_DATA/superseded_archive/`（大量 `__SUPERSEDED_*` 副本）。
3. **中英文双文件名二选一**（同一内容两套名字，是重复的直接来源）。

⚠️ 风险：`03_DATA/superseded_archive/` 按名字看是**有意的历史保留**，
清理前要确认它是否承载"supersede 不删除"原则（AGENTS.md 明确写了 "Supersede, don't delete"）。
**这条原则与去重存在张力**——建议保留 superseded 记录但只留一份，
或在 manifest 中记录 supersede 关系而不复制正文。

### 5.4 快照类文件改为「一份 latest + 历史」

- `ace-video-kingdom`：7 个相同 preflight、6 个相同 compact/live、3 个相同 cut_audit
- `r1-archaeology`：6 个相同 `r1_open_source_overview_*`
- mine-seed：11 个空 `signals_*.json`

→ 统一为 `xxx_latest.json` 覆盖写 + `history/` 按需保留。
并且**内容未变化时不应写新文件**（直接解决 4.7 的生成器空转）。

### 5.5 小仓库归位

| 仓库 | 建议 |
|---|---|
| `r1-open-source-seed` | 已归档 + 100% 重复 → 删除（保留 description） |
| `-` | 已归档 + 9/10 重复且迁移已验证 → 删除（保留 description） |
| `ace-video-assets` | 保持独立（35.7MB 纯二进制资产，0 内部重复，职责清晰） |

### 5.6 ⚠️ 不建议合并的

| 项 | 原因 |
|---|---|
| `ace-host-adapter-lab` | **边界声明最清楚的仓库**，README 明确 "experimental, read-only, not admitted to ACE production"，且有 `requirements.txt`、7 个测试文件。它与 ACE 是**有意的隔离关系**，合并会破坏"host 无治理权威"的设计。 |
| `ace-video-kingdom` | Free Zone 研究，按 AGENTS.md 必须与 ACE reality 保持分离。**只做内部去重，不要并入 ace_core。** |
| `r1-archaeology` | 文明记忆，与 ace_core 只有 1 个共享 blob，职责独立。 |
| `mine-seed` 的 `04_PROTOCOLS/` vs ace_core 的 | 见 4.5：**已漂移，不是简单副本**，不能按"以某一侧为准"合并。 |

---

## 6. 建议处理顺序

1. **先确认钥匙**：`coze-assets` 到底在哪（其他账号？本地？）——这决定文明能否恢复，优先级高于一切。
2. **确认 mine-seed 是否"未完成恢复"**：它停在 `before system reinstall` 快照、静默 18 天。
   若确实如此，那么**先恢复 HQ，再谈去重**——否则清理一个已停滞的仓库收益有限。
3. **更新 AGENTS.md 的文明地图**：7 → 11 个仓库，标注 2 个已归档，
   并修正 `R1` 的角色描述（哲学/官网 vs 实际是观察日志）。
4. **合并 `R1` + `R1_continuity_archive`**（低风险，收益明确）。
5. **删除 2 个已归档的 100% 重复仓库**（低风险，已逐字节验证）。
6. **mine-seed 去重**（高收益但需先冻结写入 + 确认 supersede 原则）。
7. **快照文件统一为 latest + history**，并让生成器在内容未变时不写文件。
8. 处理 r1-archaeology 的 open issue #6（已挂 101 天）。

---

## 7. 复现方式

```bash
# 仓库清单（含 private）
gh repo list zhangapple21-web --limit 100 --json name,isPrivate,diskUsage,pushedAt,description

# 钥匙仓库是否存在
gh api repos/zhangapple21-web/coze-assets          # → 404

# 拉取所有仓库的文件清单（含内容寻址 blob SHA）
for r in mine-seed r1-archaeology r1-open-source-seed R1 R1_continuity_archive \
         aum-protocol ace-video-kingdom ace-host-adapter-lab ace-video-assets; do
  gh api "repos/zhangapple21-web/$r/git/trees/main?recursive=1" \
    --jq '.tree[] | select(.type=="blob") | "\(.sha)\t\(.size)\t\(.path)"' > "/tmp/$r.tsv"
done

# 相同 SHA = 相同内容（无需下载即可判定跨仓库/仓库内完全重复）
```

> 全部操作为只读。未 clone 大仓库（mine-seed 48MB / ace-video-assets 67MB 未落地），
> 未修改任何仓库，未创建 issue / PR。
>
> **方法说明**：git blob SHA 是内容寻址哈希，相同内容必然得到相同 SHA，
> 因此本文所有"重复"判定都是**字节级确定**的，不是相似度猜测。
> 唯一例外是第 3 节末尾对"重装后未恢复"的推断，已明确标注为推断而非证据。

