# GitHub 变更证据桥：当前可验证事项收口

观测时间：2026-09-06T09:00:41.2158937Z（UTC）

## 已确认

- GitHub CLI 已认证为 `zhangapple21-web`；本次没有输出 token。
- `zhangapple21-web/coze-assets` 是 private 仓库，默认分支为 `main`，当前远端头为 `6acbaff8f3c57ea87b6bea35354e8cda7d0ebfd3`。
- 当前开放 Pull Request 为 0、开放 Issue 为 0；主分支 `protected=false`。
- 当前 head 没有 check-runs，commit status 返回 `pending` 但状态条目为 0；这不能解释为“检查通过”。
- 本地 clean 镜像 `C:\tmp\_audit_quarantine_coze_assets_20260905` 与远端 `main` 完全一致，状态为 `MATCH_CLEAN`。
- `C:\tmp\ace_core` 的本地 HEAD 与远端一致，但工作区有 352 个未提交条目，状态为 `MATCH_DIRTY`；该计数包含本轮新增的两份收据文件，本轮未修改既有文件。

## 必须保留的边界

- 截图中的 `add EXECUTOR and FREEZONE lineage analysis` 只能作为历史/外部界面证据；当前 API 没有对应开放 PR，因此不能声明“当前 PR 已审查或已合并”。
- `SECRET.md` 已不再被跟踪，且 `01_credentials/` 在忽略规则中；但 `02_miner_config/miner_env.sh` 仍被跟踪，并检测到 32 个非占位导出。没有回显任何值，因此这里只能标为 `REVIEW_REQUIRED`，不能断言这些值全部是真实密钥或全部已失效。
- GitHub ruleset REST 端点返回 private-repository plan 的 403；因此当前不能从 API 证明规则集配置，更不能把网页上曾见过的 disabled/0 targets 状态当成活动准入层。

## 收口结论

本轮结论是 `CLOSED_WITH_GAPS`：API、仓库头、PR/Issue/check、local-remote parity 与不泄密扫描都已完成；没有进行合并、推送、权限修改、密钥轮换或历史重写。

下一步只有一件高价值事项：在独立、受审查的变更中核验并轮换 `miner_env.sh` 中的真实值，再从仓库内容和历史中清除；完成前不能把 coze-assets 视为“密钥边界已收口”。

机器可读收据：`research/decision_records/github_change_bridge_closure_20260906.json`
