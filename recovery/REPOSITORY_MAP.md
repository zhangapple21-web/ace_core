# Repository Map

更新日期：2026-10-01；当前远程 ref 观测时间：2026-10-01T06:02:34Z–2026-10-01T06:02:37Z。此表覆盖 `restore_from_remote.py` 当前明确列出的 core、state、video 和全部 16 个 OPTIONAL_REPOS，不代表整机资产或完整跨仓依赖图。

## 当前远程 ref 与历史演练

本次 `ls-remote --heads` 查得：core `core/daemon-lifecycle-resilience-20260912` 当前 SHA `4d40191b539dfcc0e651504437e20d07daa5dd4e`，state `main` 当前 SHA `a40340bf1329b3789773ce09d2cd11a50676f5da`，video `main` 当前 SHA `27da48891ac778e88689fd1e33cdc058472f9b90`；三项均 `EXISTS`、exit=0。以下表格仅记录历史已演练 SHA，不能当作当前 HEAD。core 当前 HEAD 的完整恢复结果为 `UNVERIFIED`，本次未重跑恢复。state 从既有隔离 checkout 的当前远程 SHA 对象复核 manifest hash/count：1674 files、65 evidence files、37960831 bytes，与下表证据一致；未重新推送 state。

| Repository | Branch | Credential-free URL | 已演练 SHA | 范围 |
|---|---|---|---|---|
| `ace_core` | `core/daemon-lifecycle-resilience-20260912` | https://github.com/zhangapple21-web/ace_core.git | `4414401034b1040351b45f60cbbbb8afdb8ef434` | 远程 clone、bootstrap、status；总体 PARTIAL |
| `ace-civilization-backup` | `main` | https://github.com/zhangapple21-web/ace-civilization-backup.git | `a40340bf1329b3789773ce09d2cd11a50676f5da` | 私有 state；1674 个白名单文件 hash PASS；需授权访问，不是凭据仓 |
| `ace-video-kingdom` | `main` | https://github.com/zhangapple21-web/ace-video-kingdom.git | `27da48891ac778e88689fd1e33cdc058472f9b90` | 历史远程演练：36 项离线测试及 dry-run；不提交 Provider；当前 state 演练未含视频 |

core SHA 是恢复代码演练版本，不是本文档发布后的动态 HEAD。state 恢复由显式 state 选项启用；视频由 `--with-video` 启用。精简可复核摘要见 `BACKUP_COMPLETENESS_MANIFEST.json` 的 `remote_restore_evidence`。

## 可选仓库完整列表

Observed-at：2026-10-01T06:02:34Z–2026-10-01T06:02:37Z。2026-10-01 非交互执行 `git -c credential.interactive=false ls-remote --heads URL BRANCH`；设置 `GIT_TERMINAL_PROMPT=0`、`GCM_INTERACTIVE=Never`，每仓 timeout=30s。以下 16 项状态均为 `EXISTS`，exit=0 且唯一分支 HEAD；`ACCESS_BLOCKED`=不可访问、`BRANCH_MISSING`=成功查询但分支不存在、`UNVERIFIED`=超时或无法验证，失败时当前 SHA 为 UNKNOWN；仅证明 ref 可查询，不证明内容已恢复、测试通过或运行时已加载。失败、超时、空结果须记 UNKNOWN，不沿用历史截短 SHA。

| Repository | Branch | Credential-free URL | Observed HEAD | 用途 / 范围 |
|---|---|---|---|---|
| `mine-seed` | `main` | https://github.com/zhangapple21-web/mine-seed.git | `60b8adbd85dea63c09e35ad48b326a6f18aeefdd` | 可选 seed；不同于凭据仓 |
| `ace-capability-registry` | `main` | https://github.com/zhangapple21-web/ace-capability-registry.git | `67e49a226ea404f02a209f4188bc8d4cf81ba1e6` | 能力登记 |
| `ace-skill-vault` | `main` | https://github.com/zhangapple21-web/ace-skill-vault.git | `8468afa336aee75f23e097b5c0a8859f8cf0a7e2` | Skill 资产 |
| `ace-knowledge-forge` | `master` | https://github.com/zhangapple21-web/ace-knowledge-forge.git | `9a383989aa10a93996cbfd093ac89496a0c69545` | 知识锻造 |
| `ace-salvage` | `main` | https://github.com/zhangapple21-web/ace-salvage.git | `22759c180d70452562769af9a091a1e157fafd44` | 抢救工具 |
| `ace-structure-steward` | `main` | https://github.com/zhangapple21-web/ace-structure-steward.git | `7aa9b95e824c51a883b19ec1d5c6fad37aa7c456` | 结构治理 |
| `ace-task-queue` | `main` | https://github.com/zhangapple21-web/ace-task-queue.git | `005845816f1bff67a2e795b5c5a7326286cc4509` | 独立队列实验，非当前 TaskPool 真源；local changes 未验 |
| `ace-video-assets` | `main` | https://github.com/zhangapple21-web/ace-video-assets.git | `59d81bf94dfe98a3709587025cf4aa7c21862208` | 公开参考资产，不含私有素材 |
| `r1-continuity-backup` | `main` | https://github.com/zhangapple21-web/r1-continuity-backup.git | `8246287a7d8b74d7d2aa07ec2b3e1dd1cace214e` | 可选历史仓，非本次 state 真源 |
| `r1-archaeology` | `main` | https://github.com/zhangapple21-web/r1-archaeology.git | `901a267b5f9b932ee967bec7ea4b2252607418b4` | 历史考古 |
| `R1_continuity_archive` | `main` | https://github.com/zhangapple21-web/R1_continuity_archive.git | `3b45edbb9d75a8548352ca969336ed1e8ed2aab7` | 历史归档 |
| `R1` | `main` | https://github.com/zhangapple21-web/R1.git | `c852b6212e66725d0710836bfb2e5670a058764f` | 可选历史域 |
| `claw-soul` | `main` | https://github.com/zhangapple21-web/claw-soul.git | `573c17d612b40d7bfc737aa18e6660e0dcfdeafa` | 股票等工具；历史私有路径身份 UNKNOWN |
| `aum-protocol` | `main` | https://github.com/zhangapple21-web/aum-protocol.git | `c4ed2ea371c1f791a8c3cfb52d3a5925d4ee50fa` | 可选协议 |
| `r1-open-source-seed` | `main` | https://github.com/zhangapple21-web/r1-open-source-seed.git | `1dc82c84a960eb7030e966313dd2d8e92ebf3df4` | 可选 seed |
| `coze-assets` | `main` | https://github.com/ACEE0011/coze-assets.git | `6acbaff8f3c57ea87b6bea35354e8cda7d0ebfd3` | 可选 Coze 资产；注意 owner 不同 |

optional 仅在显式 `--with-optional` 时 clone，不自动发现。本次仅查 ref，不 clone optional。

## 人工安全恢复边界

`mine-seed-credentials`：branch `main` 为历史地图记录，当前 ref 为 UNKNOWN；credential-free URL 为 https://github.com/zhangapple21-web/mine-seed-credentials.git 。本任务未查询、读取或备份其内容；仅由安全来源人工恢复，不列入 OPTIONAL_REPOS。

## 证据支持的依赖方向

- `ace_core -> video consumer/dispatch`：核心消费者接口，视频能力由独立仓库负责，真实 Provider 未验。
- `ace_core -> skills/registry`：可选扩展方向，自动运行时加载 UNKNOWN。
- `ace-skill-vault:stock-analysis-client-workflow -> ace_core:core/ultrashort_playbook.py`：历史验证调用纯 helper。
- `ace-skill-vault:stock-analysis-client-workflow -> claw-soul:stock_query.py`：声明的可选工具，私有历史路径身份 UNKNOWN。
- `ace-capability-registry -> ace-skill-vault:SKILL.md`：历史 loadable 检查。

五个历史验证 checkout 无 gitlink 或 `.gitmodules` 不等于全仓图完整；统一跨仓 build DAG 为 UNKNOWN。

## 未知和未恢复项

C/D 扫描截断；X/Y 是 D 子目录模拟映射，不是独立介质。整机资产覆盖 UNKNOWN/PARTIAL。白名单任务、知识、runtime 和 memory index 已从私有 state 恢复，但跨文件事务一致性、继承 epoch 和行为连续性未验；不能继续声称所有历史状态均未备份，也不能反推所有历史状态可恢复。排除项含 300 个 raw HTML（仅 hash，无正文），15152 个 backup/cache/test/validation/claim 文件、5 个源码或临时进程状态文件。密钥、私有媒体和白名单范围外资产不在恢复保证内。

daemon 未启动，每日迭代、计划任务动作未验；Skill 宿主 E2E 未验，模拟单不存在。生产 `C:\tmp\ace_core` 不覆盖；旧 3000/3002、legacy scheduler/heartbeat 不恢复。禁止 force-push、破坏性重置或将 dirty clone 当真源。
