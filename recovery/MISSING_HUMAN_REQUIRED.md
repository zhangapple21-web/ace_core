# Missing / Human Required

更新日期：2026-10-01。总体 `PARTIAL`。区分白名单已恢复、明确未备份和未知范围；不宣称整机完整。

## 已验证范围

私有 `ace-civilization-backup` main `a40340bf1329b3789773ce09d2cd11a50676f5da` 已从远程恢复：1674 个白名单文件 hash PASS，含 796 tasks、686 knowledge files（612 loaded records）、192 runtime files、7457 memory index records。两次匹配盘点不是跨文件事务快照，继承 epoch、历史行为连续性及所有历史 DB/日志是否覆盖为 UNKNOWN。

## 未备份或人工补回

| 项目 | 状态 | 证据边界 / 恢复要求 |
|---|---|---|
| Provider API key/token/password、用户密钥 | `SECRET_REQUIRED / NOT_BACKED_UP` | 未读取、未备份、未上传；由安全来源人工注入，不可从 Git 恢复。 |
| `mine-seed-credentials` 私密仓内容 | `SECRET_REQUIRED / NOT_BACKED_UP` | 不属于公开恢复链；本任务未查询或读取。禁止把真实值写入 Git、日志或收据。 |
| Miner/CredentialManager 私密目录 | `SECRET_REQUIRED / NOT_BACKED_UP` | 真实目录和凭据从安全来源补回。 |
| CosyVoice 权重、参考说话人音频、私有媒体/缓存 | `HUMAN_REQUIRED` | 未进入本次恢复保证；按授权来源重新取得并登记 hash/许可。 |
| 300 个 raw external HTML 正文 | `HASH_ONLY / NOT_RECOVERABLE_FROM_SNAPSHOT` | hash 留存，正文未上传；原源可重新取得与否为 UNKNOWN。 |
| 15152 个 backup/cache/test/validation/claim 文件 | `EXCLUDED` | 不进入本次 state snapshot，不能承诺从本快照恢复。 |
| 5 个 source/transient process state 文件 | `EXCLUDED` | 不从 state 恢复；daemon heartbeat、claim/lease 等不可作为已恢复运行态。 |
| 白名单外历史 DB/追加日志、用户私有资产 | `UNKNOWN / OUT_OF_SCOPE` | 不能从白名单计数推出全部历史已备份，也不能声称全部历史均不可恢复。 |
| 计划任务动作值、启动参数、绝对路径引用 | `UNVERIFIED` | 未检查，不宣称动作安全或计划任务已恢复。 |
| `C:\Users\Administrator\.codex\skills` | `OPERATOR_ENVIRONMENT_REQUIRED` | 按安装源和版本重新安装，不整体复制为 ACE runtime。 |
| `D:\Trae` | `OPERATOR_ENVIRONMENT` | 应用安装目录，不进入恢复链。 |
| 旧 `3000/3002`、legacy scheduler/heartbeat | `ARCHAEOLOGY_ONLY` | 不恢复、不启动、不作为健康前置。 |

## 剩余验收限制

C/D 扫描截断：C 159268、D 138394，均 `truncated=true`；X/Y 是 D 子目录模拟映射。整机完整性和本地关键单点均 UNKNOWN。

当前远程 bootstrap `PARTIAL`、exit `3`，测试 `SKIP (--skip-tests)`；health exit `2`，1 error/1 warning。daemon 未启动，heartbeat、每日迭代、继承 epoch 行为、计划任务动作未验；不做 daemon 视频交易或真实视频任务。

历史业务验证 `FAIL`：股票 time 字段语义缺陷未修复；有报价但没有模拟单。5 个 Skill 加载检查和一次纯 helper 调用不是宿主 E2E。视频只有历史 36 项离线测试与 dry-run，不出片、不提交 Provider。

最小可复核摘要与回执 hash 已内嵌在 `BACKUP_COMPLETENESS_MANIFEST.json`，不依赖公开仓中不存在的本地收据文件来宣称完整。
