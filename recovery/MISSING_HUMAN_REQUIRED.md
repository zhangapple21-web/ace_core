# Missing / Human Required

基线日期：2026-09-30

这些项目不能公开上传，但恢复时必须从安全来源补回。它们不是核心离线复活的隐藏前置；未补回时必须明确标记为受限，不得伪造 Provider 能力已恢复。

| 项目 | 标记 | 来源/变量 | 恢复方式 |
|---|---|---|---|
| Provider API key/token/password | `SECRET_REQUIRED` | 各 Provider 官方密钥管理器；环境变量名以代码和私密仓为准 | 在新机器私密环境变量注入，禁止写入 Git、日志和收据 |
| `mine-seed-credentials` 私密仓内容 | `SECRET_REQUIRED` | 私有 Git/密码管理器 | 人工 clone 并核对；本任务不提交本地 `.env` 变更 |
| Miner/CredentialManager 私密目录 | `SECRET_REQUIRED` | `ACE_MINER_ASSETS_PATH` 或安全目录 | 恢复后写入本地配置，不上传真实值 |
| CosyVoice 权重与参考说话人音频 | `HUMAN_REQUIRED` | 官方模型源与已授权音频 | 重新下载/登记 hash 与许可；不进入公开仓 |
| 私有参考图、视频、音频、渲染缓存 | `HUMAN_REQUIRED` | 获授权的 D 盘资产库或对象存储 | 选择性恢复并登记 hash/许可；不作为核心源码依赖 |
| TaskPool、lease、MemoryIndex、daemon heartbeat 历史状态 | `REBUILDABLE` 或连续性需要时 `HUMAN_REQUIRED` | 远程源码 + 脱敏收据/快照 | 默认空结构重建；只在确需历史连续性时导入 |
| `C:\\Users\\Administrator\\.codex\\skills` | `OPERATOR_ENVIRONMENT_REQUIRED` | Codex/Skill 安装源与版本 | 新机器按需安装；不整体复制为 ACE runtime |
| `D:\\Trae` | `OPERATOR_ENVIRONMENT` | Trae 安装程序 | 不是 ACE 仓库，不进入恢复链 |
| 旧 `3000/3002`、legacy scheduler/heartbeat | `ARCHAEOLOGY_ONLY` | 历史文档 | 不恢复，不启动，不作为健康检查前置 |

## 当前阻断项

- `LOCAL_ONLY_CRITICAL = 0`（基于 C:/D: 盘点、canonical 仓库核对和独立恢复演练）。
- 如果未来审计发现某个行为关键文件只存在于非 canonical clone、未提交工作树或 ignored 路径，必须立即将其改列为 `LOCAL_ONLY_CRITICAL` 并把总体状态降为 `PARTIAL / BLOCKED`。
