# Missing / Human Required

基线日期：2026-09-30

以下内容不应进入公开 Git，但恢复 ACE 时必须由人或安全系统补回。没有这些内容时，核心结构和离线测试仍应可运行；需要外部模型/媒体 Provider 的能力会保持 `BLOCKED`，不得伪造已恢复。

| 项目 | 标记 | 来源/变量 | 恢复方式 | 当前证据 |
|---|---|---|---|---|
| Provider API keys / tokens | `SECRET_REQUIRED` | `OPENAI_API_KEY`、各 Provider 环境变量；以本机安全管理器为准 | 在新机器的私密环境变量中注入；不写 `.json`、日志、收据 | 仓库代码从环境/私密凭据目录读取；公开仓未发现真实 key 模式 |
| `mine-seed-credentials` 内容 | `SECRET_REQUIRED` | 私有 Git 仓或密码管理器 | 人工 clone 私有仓并核对提交；禁止从工作区未提交 `.env` 直接公开推送 | 本机仓存在未提交 `.env` 与备份文件，未纳入本次提交 |
| `private_coze-assets` / miner credentials | `SECRET_REQUIRED` | `ACE_MINER_ASSETS_PATH` 或私密目录 | 恢复到本机私密目录；让 CredentialManager 自动发现/读取 | `ace_config.json` 不再把 C/D 盘路径视为远程真源 |
| CosyVoice 模型权重、参考说话人音频 | `HUMAN_REQUIRED` | 官方模型源 + 本人/书面授权的参考音频 | 重新下载并登记许可、hash、授权范围；不要上传公开仓 | 权重位于 `D:\视频创作\runtimes`，仓库未跟踪 |
| 私有参考图、视频、音频、渲染缓存 | `HUMAN_REQUIRED` | 获授权的 D 盘资产库或安全对象存储 | 只恢复获准资产；按项目收据登记 hash/许可 | Git 忽略媒体与 `media_staging`，这是有意边界 |
| 运行态 TaskPool / lease / memory index | `REBUILDABLE`（若需历史连续性则 `HUMAN_REQUIRED`） | 远程源码 + 已导出收据；历史状态安全快照 | 先用空结构启动；仅在需要历史连续性时导入脱敏快照 | `task_pool/`、`02_MEMORY/`、`06_RUNTIME/ace/` 被 gitignore，当前统计见 manifest |
| `ace-task-queue` 本地领先提交 | `LOCAL_ONLY_NONCORE` | 本机仓 `C:\tmp\_d2dd_r49_sandbox` | 人工审阅后合并/归档；本任务不把它当当前 ACE 真源 | 本地 `origin/main..HEAD` 领先 4 commits |
| 旧 3000 / 3002 路径 | `ARCHAEOLOGY_ONLY` | 历史文档/证据 | 不恢复为生产依赖；如需研究仅在隔离考古环境复现 | 本基线明确排除 |

## 当前是否存在 LOCAL_ONLY_CRITICAL

在本次审计的核心运行时定义中，**未确认存在**已知 `LOCAL_ONLY_CRITICAL`；但由于两个核心仓库在审计开始时都有大量未提交修改，只有提交、推送、隔离 clone 和恢复演练完成后，才能把该结论升级为事实。

## 恢复后的人工检查

1. 确认私密凭据来源不是浏览器/聊天记录中的散落副本。
2. 逐项记录授权、许可、撤回方式和文件 hash。
3. 将新机器的本地路径写入未跟踪的 `ace_config.local.json`（如确有需要），不修改远程模板。
4. 任何无法从远程、安全仓或可重建脚本得到的关键文件，必须标记 `LOCAL_ONLY_CRITICAL` 并阻断 PASS。
