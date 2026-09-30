# Repository Map

基线日期：2026-09-30

| Repository | Purpose | Canonical branch/ref | Remote | Last known good / verified | State | Recovery entry |
|---|---|---|---|---|---|---|
| `ace_core` | 当前 ACE 核心运行时、TaskPool、Worker/lease/fencing、Memory、协议、schema、测试、恢复 | `core/daemon-lifecycle-resilience-20260912` | `https://github.com/zhangapple21-web/ace_core.git` | remote HEAD `14f48ff4631ee6431c5127aece4f46acb3edb60d`; behavior baseline `2ce7f9068441c0d341d8ed26cec1ea77d72cdbf8` | canonical | `recovery/restore_from_remote.py`, `recovery/bootstrap.py` |
| `ace-video-kingdom` | 视频能力域、门禁、模型/能力路由、规则、测试、入口 | `main` | `https://github.com/zhangapple21-web/ace-video-kingdom.git` | `27da48891ac778e88689fd1e33cdc058472f9b90` | canonical（本地未跟踪项目资产不进入核心链） | `recovery/ACE_VIDEO_RECOVERY_POINTER.md` |
| `ace-capability-registry` | 能力登记与审计工具 | `main` | `https://github.com/zhangapple21-web/ace-capability-registry.git` | `67e49a226ea404f02a209f4188bc8d4cf81ba1e6` | optional extension | 单独 clone |
| `ace-skill-vault` | Skill 资产与依赖图 | `main` | `https://github.com/zhangapple21-web/ace-skill-vault.git` | `8468afa336aee75f23e097b5c0a8859f8cf0a7e` | optional extension | 单独 clone |
| `ace-knowledge-forge` | 知识锻造 | `master` | `https://github.com/zhangapple21-web/ace-knowledge-forge.git` | `9a383989aa10a93996cbfd093ac89496a0c69545` | optional knowledge | 单独 clone |
| `ace-salvage` | 保全/抢救工具 | `main` | `https://github.com/zhangapple21-web/ace-salvage.git` | `22759c180d70452562769af9a091a1e157fafd44` | optional governance | 单独 clone |
| `ace-structure-steward` | 结构治理/审计 | `main` | `https://github.com/zhangapple21-web/ace-structure-steward.git` | `7aa9b95e824c51a883b19ec1d5c6fad37aa7c456` | optional governance | 单独 clone |
| `ace-video-assets` | 已发布公开视频参考资产 | `main` | `https://github.com/zhangapple21-web/ace-video-assets.git` | `59d81bf94dfe98a3709587025cf4aa7c21862208` | optional public asset | 单独 clone |
| `R1_continuity_archive` | 历史/考古知识 | `main` | `https://github.com/zhangapple21-web/R1_continuity_archive.git` | `3b45edbb9d75a8548352ca969336ed1e8ed2aab7` | optional archaeology | 单独 clone |
| `mine-seed-credentials` | 私密凭据仓 | `main` | `https://github.com/zhangapple21-web/mine-seed-credentials.git` | private; not part of public restore | `SECRET_REQUIRED` | 由安全仓/密码管理器人工恢复 |
| `ace-task-queue` | 独立队列实验；不是当前 ACE TaskPool 真源 | `main` | `https://github.com/zhangapple21-web/ace-task-queue.git` | local-only changes未验证 | optional / do not depend | 人工审阅后决定归档或合并 |

## 本地非真源环境分类

- `C:\\Users\\Administrator\\.codex\\skills`：Agent/Codex 操作环境；不整体上传，不作为 ACE runtime。若某 Skill 是视频能力的必要依赖，需记录安装来源/版本并在恢复时重新安装。
- `D:\\Trae`：应用安装目录，不是 ACE 仓库；不进入恢复链。
- `D:\\tmp`、`C:\\tmp` 的历史 clone、演练目录、quarantine、缓存和日志：仅证据/考古；不得被恢复脚本读取或作为真源。

## 分支治理

禁止 force-push、reset --hard 或将非 canonical 工作区当真源。任何删除/合并先在空目录完成恢复演练。历史 `3000/3002` 与 legacy scheduler/heartbeat 不恢复。
