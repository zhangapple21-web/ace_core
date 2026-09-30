# Repository Map

基线日期：2026-09-30

| Repository | Purpose | Canonical branch / ref | Remote | Last known good commit（当前已验证） | Current state | Recovery entry |
|---|---|---|---|---|---|---|
| `ace_core` | ACE 当前认知运行时；AceDaemon、TaskPool、Worker/lease/fencing、Researcher/Validator/Guardian/Archivist、MemoryGateway/MemoryIndex、协议、schema、测试、恢复 | `core/daemon-lifecycle-resilience-20260912`（当前工作分支；不得误用 `main`） | `https://github.com/zhangapple21-web/ace_core.git` | `92fc44f`（远程已存在；灾备提交待推送） | 当前工作树有大量已审阅前的修改；无 stash；无本地独有 commit | `recovery/bootstrap.ps1` |
| `ace-video-kingdom` | ACE 视频能力域；生产控制面、门禁、角色/场景/镜头合同、模型路由、测试、视频规则 | `main` | `https://github.com/zhangapple21-web/ace-video-kingdom.git` | `a7e9468`（远程已存在；灾备提交待推送） | 当前工作树有大量修改/未跟踪研究资产；媒体与缓存仍本地 | 仓库 README + `recovery/ACE_RECOVERY_MAP.md` |
| `ace-video-assets` | 已发布的公开视频参考资产（可选） | `main` | `https://github.com/zhangapple21-web/ace-video-assets.git` | `59d81bf` | clean；不阻塞核心复活 | 单独 clone；按视频项目合同选择性恢复 |
| `R1_continuity_archive` | 历史/考古知识（可选） | `main` | `https://github.com/zhangapple21-web/R1_continuity_archive.git` | `3b45edb` | clean；不阻塞核心复活 | 单独 clone；只作为知识资产 |
| `mine-seed-credentials` | 私密凭据仓（不可公开复制） | `main` | `https://github.com/zhangapple21-web/mine-seed-credentials.git` | `68f6bb0` | 本地存在未提交凭据变更；必须人工审计，禁止本任务自动 push | 仅从私密仓/密钥管理器恢复，见 `MISSING_HUMAN_REQUIRED.md` |
| `ace-task-queue` | 独立任务队列实验仓（可选/非当前 ACE 生产真源） | `main` | `https://github.com/zhangapple21-web/ace-task-queue.git` | `e3d20d6`（本地领先 origin/main，未推送） | `LOCAL_ONLY_NONCORE`；不得当作当前 TaskPool 真源 | 先人工审阅本地领先 4 commits，再决定合并/归档 |

## 分支治理

- 当前 ace_core 的工作分支不是远程默认 `main`；恢复脚本必须显式 checkout 该分支或其灾备 tag。
- 任何把工作分支合并到 `main` 的动作都必须先通过隔离恢复演练；禁止 force-push、reset --hard 或删除旧分支。
- 旧 `3000` / `3002` 路径只可在考古文档中出现；不能进入新的恢复入口、health check 或生产依赖。
