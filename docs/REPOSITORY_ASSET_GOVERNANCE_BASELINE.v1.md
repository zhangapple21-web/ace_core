# ACE Repository / Asset Governance Baseline v1.0

**盘点时间：** 2026-09-29（Asia/Shanghai）  
**目的：** 在不损失唯一能力、唯一证据和可恢复性的前提下减少物理重复。  
**本轮性质：** 仓库/资产治理；不改变生产入口、默认模型、TaskPool 状态机或视频生产合同。

## 决策标签

| 标签 | 含义 |
| --- | --- |
| `KEEP` | 当前真源、生产消费者、唯一资产或唯一证据，继续保留。 |
| `MERGE` | 已证明同一职责、同一消费者边界和可回读迁移路径，合并后只留一个真源。 |
| `ARCHIVE` | 不再是活跃入口，但保留压缩包/快照/收据，供历史和恢复使用。 |
| `DELETE` | 已证明无生产消费者、无独特资产/证据、远程或归档恢复点存在；本地副本送入回收站。 |

## 生产真源与必须独立的仓库

| 对象 | 决策 | 结论与证据 |
| --- | --- | --- |
| `C:\\tmp\\ace_core` | `KEEP` | 唯一现代 ACE Runtime；`AceDaemon` 承载生产生命周期，`TaskPool` 是任务状态权威。当前工作区有大量在途改动，本轮不清理、不重置、不提交。 |
| `D:\\视频创作\\ace-video-kingdom` | `KEEP` | 视频生产唯一入口和合同/门禁真源；与 ACE Runtime 职责不同，不能合并。工作区有在途改动，本轮不触碰。 |
| `C:\\轻量项目\\ace_task_queue` | `KEEP` | TaskPool 协调协议、卡片和生命周期证据的独立仓；当前有在途卡片改动，不与 `ace_core` 合并。 |
| `C:\\轻量项目\\ace_knowledge_forge` | `KEEP` | 知识/考古归档真源；与 Runtime 和 TaskPool 不同职责，不能合并。仓库干净，远程可恢复。 |
| `C:\\轻量项目\\ace_capability_registry` | `KEEP` | 能力注册与依赖证明真源；内部 `state\\_r20_repocheck` 是被测试脚本直接消费的夹具沙箱，必须继续独立保留。 |
| `C:\\轻量项目\\ace_salvage` | `KEEP` | 恢复/保全资产真源，不能并入运行时。 |
| `C:\\轻量项目\\ace_skill_vault` | `KEEP` | Skill 清单与验证证据真源，不能并入 Runtime。 |
| `C:\\轻量项目\\ace_structure_steward` | `KEEP` | 结构治理/归属审计真源，不能并入 TaskPool 或 Runtime。 |
| `D:\\视频创作\\temp\\ace-video-assets` | `KEEP` | 本地视频资产 canonical checkout；生产文件引用远程公开资产 URL，保留一个本地 checkout 便于回读。 |
| `D:\\视频创作\\temp\\_archive\\20260928\\ace-video-assets_ep01_exact` | `KEEP` | 远程独立 `ep01-exact-audio-20260918T171515Z` 分支，包含当前主线没有的精确音频资产；不可合并删除。 |
| `D:\\视频创作\\runtimes\\cosyvoice3\\CosyVoice` | `KEEP` | 当前 CosyVoice 运行时，含本地环境/模型资产；不与研究 clone 合并。 |
| `D:\\视频创作\\voice_research\\ChatTTS_20260920` | `KEEP` | 语音研究/模型资产 checkout，含本地非 Git 资产；不是代码重复垃圾。 |
| `D:\\视频创作\\temp\\drama-skills-readonly-20260929` | `KEEP` | `zenstory-ai/drama-skills` 的唯一本地参考 checkout；固定提交 `4e48ccbf...`。 |

## 已执行的物理减法

| 对象 | 决策 | 执行与恢复点 |
| --- | --- | --- |
| `C:\\Users\\Administrator\\Documents\\Qoder\\2026-09-29\\4d16d943\\drama-skills` | `DELETE` | 与上面的 canonical checkout 同远程、同提交、无脏改动、无独有文件；本地副本送入回收站。远程提交 `4e48ccbf0f77da757d7cacc6937b1cc59c124845` 可恢复；删除清单在 `C:\\Users\\Administrator\\Documents\\Qoder\\_archive\\20260929\\drama_skills_duplicate_delete.json`。 |
| `D:\\视频创作\\quarantine\\tts_compare_20260916\\ChatTTS` | `DELETE` | 与 `voice_research\\ChatTTS_20260920` 同提交、干净、无独有 Git 文件；本地副本送入回收站。远程提交可恢复；清单在 `duplicate_voice_clones_delete.json`。 |
| `D:\\视频创作\\quarantine\\tts_compare_20260916\\CosyVoice` | `DELETE` | 与运行时 CosyVoice 同提交、干净、无独有 Git 文件；只删除研究 clone，运行时和模型不动。清单在 `duplicate_voice_clones_delete.json`。 |
| `D:\\视频创作\\temp\\ace-video-assets_upload_ep01_v3` | `DELETE` | 干净；HEAD `08ac2c4c...` 已是远程 `origin/main` 的祖先，内容已进入远程主线；没有本地独有未提交资产。本地 clone 送入回收站，清单在 `ace_video_assets_upload_ep01_v3_delete.json`。 |
| `D:\\视频创作\\temp\\ai-film-skills` | `DELETE` | 干净的外部参考 clone；生产只引用 GitHub URL，方法已登记在视频王国 `research/REFERENCE_MINES.md`，没有本地独有资产。提交 `4a33628b789976f004079772c8dc77d3f317a566` 可由远程恢复；清单在 `ai_film_skills_delete.json`。 |
| `C:\\Users\\Administrator\\Documents\\Qoder\\2026-09-25-f41ea0e2` | `ARCHIVE` | 11 个旧探针文件含独有审计脚本/输出，不能丢；已逐文件 SHA-256 校验后压缩为 `qoder_20260925_f41ea0e2_probe.zip`（SHA-256 `655B567CBAE5386BAD8F302E08A4495AFD74A46FD498EC7911E927F93DE99B45`），并保留逐文件索引 `qoder_20260925_f41ea0e2_probe.inventory.json`；活跃路径已移除。 |
| `C:\\Users\\Administrator\\Documents\\Qoder\\_mirror_d2dd5b01\\2026-09-27...2026-09-29T0903` | `ARCHIVE` | R60 历史 38 跳、2727 文件、76171545 字节，逐文件哈希回读后压缩为 `R60_historical_hops_before_20260929T1011.zip`（SHA-256 `D7BCCD7088F0B93A2489A19F62A536052C2F22C639E8959206DEB77EF73BA7BF`），并保留 `R60_historical_hops.inventory.json`；历史目录送入回收站。 |
| `C:\\Users\\Administrator\\Documents\\Qoder\\2026-09-25\\d2dd5b01\\_exec\\_d2dd_r60f_mirror.py` | `ARCHIVE` | 一次性 R60 镜像工具，没有 ACE/计划任务消费者；按 SHA-256 `067BAF1DCB8FCA24407734536902D1766BB7BEBD03DB0A1BCFA68C1DA48C572` 归档，最新 R60 快照中的脚本和收口收据保留。 |
| `C:\\Users\\Administrator\\Documents\\Qoder\\_mirror_d2dd5b01\\2026-09-29T1011` | `KEEP` | R60 最新完整跳，作为唯一当前镜像和恢复入口；不再继续追加旧跳副本。 |

## 外部研究仓库：保留一份参考，不进入生产

以下对象没有发现 ACE/视频生产消费者，也没有同职责的本地真源；它们已经位于 `quarantine/` 或 `research/`，统一视作 `ARCHIVE`，不复制到主仓、不接入生产入口：

- `D:\\视频创作\\research\\external_agnes_repos_20260915\\*`
- `D:\\视频创作\\quarantine\\quartz_reference_20260921`
- `D:\\视频创作\\quarantine\\rvc_runtime\\RVC-WebUI`
- `D:\\视频创作\\quarantine\\tts_compare_20260916\\fish-speech`
- `D:\\视频创作\\quarantine\\tts_compare_20260916\\edge-tts`
- `D:\\视频创作\\voice_research\\AnimeVox_20260920`

它们是外部参考矿，不是生产依赖；需要再次使用时从远程提交或本地归档恢复，禁止从中静默创建第二入口。

## 统一状态标签（运行时与工具）

| 组件 | 状态标签 | 说明 |
| --- | --- | --- |
| `AceDaemon` | `ACTIVE / SOLE_MODERN_RUNTIME` | 唯一现代生产运行时。 |
| `TaskPool` | `ACTIVE / SOLE_PRODUCTION_LIFECYCLE` | 任务状态、lease、claim、fencing、recovery 的权威；不与旧 scheduler/task_queue 并列。 |
| `Worker Capsule` | `ACTIVE_SUPPORT / EXPLICIT_DRILL_AND_CLI` | 使用同一个 TaskPool 的恢复/演练端口；不是第二运行时，也不是默认 daemon 替代品。 |
| `ops/` | `KEEP_SUPPORT / AUDIT_AND_DRILL` | 测试、审计、恢复演练和只读验证工具集合；不是独立生产 runtime，不整体删除。 |
| `core/scheduler.py` | `KEEP / FAIL_CLOSED_TOMBSTONE` | 已退役、显式抛出 `legacy_runtime_deprecated`；测试和文档依赖这个失败语义，不能删除后改成导入错误。 |
| `core/task_queue.py` | `KEEP / FAIL_CLOSED_TOMBSTONE` | 同上；保留为退役边界，不产生任务。 |
| R60 一次性镜像工具 | `ARCHIVE / RETIRED` | 最新快照和收据保留，活跃工具源已归档。 |
| `core/miner_pool`（文件头标记 deprecated） | `KEEP / ACTIVE_COMPATIBILITY` | `ace_daemon.py` 仍直接构造 `MinerPool`，所以现在不能删；先保留现役兼容路径，待有完整迁移证据再收口。 |
| `core/survival_loop/engine.py` | `KEEP / RESEARCH_OR_COMPATIBILITY` | 与 `MinerPool` 存在历史替代关系，但当前固定回退链不能证明等价；本轮不合并、不静默换路。 |

## 合并结论

本轮没有安全的 `MERGE` 候选。四个主仓、TaskPool、Worker Capsule、ops、视频资产和知识/技能/结构仓职责边界不同；把它们“合成一个仓”会损失消费者边界和恢复语义。唯一可做的物理合并是重复 checkout 的消除，已按 `DELETE`/`ARCHIVE` 执行，而不是改 Git 远程历史。

## 安全边界与未做事项

- 没有删除远程仓库、远程分支或任何主线提交。
- 没有对四个主仓执行 `reset`、`checkout`、批量提交或覆盖未提交工作。
- 没有删除 `_r20_repocheck`、视频成片/音频、角色资产、运行时模型或唯一历史收据。
- 回收站中的 DELETE 对象仍可恢复；归档包有独立 SHA-256 收据。
- 本轮只做仓库/资产减法治理；不把“外部参考仓存在”误报为生产能力。

## 验收口径

1. 生产真源只有 `ace_core`、`ace-video-kingdom` 及其明确协作/资产仓；没有新建第二 Scheduler、第二 TaskPool 或第二视频入口。
2. `core/scheduler.py`、`core/task_queue.py` 的 fail-closed 语义保持不变。
3. R60 镜像目录只剩最新完整跳；历史可由压缩包和哈希清单恢复。
4. 相同远程/相同提交的重复 clone 已物理移出活跃工作区；有分支差异或本地模型资产的 clone 仍独立保留。
5. 本文是治理索引，不授予任何生产执行权限；后续改变状态必须新增证据并更新本表。
