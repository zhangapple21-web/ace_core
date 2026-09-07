# ACE 数据源复核与能力分级（2026-08-27）

## 结论

此前将腾讯和东方财富整体判为淘汰过于粗糙。供应商必须按 operation 分级，不能因一个 host 或一个端点失败连坐所有能力。

## 直接证据

* `qt.gtimg.cn/q=sz000001`：HTTP 200，返回实时 quote。
* `ifzq.gtimg.cn/appstock/app/kline/mkline`：HTTP 200；本机实测返回 482 条 1 分钟数据，最新 bar 时间为 202608271046。
* `web.ifzq.gtimg.cn/...`：DNS 失败；旧代码使用该 host，属于明确的路径/域名故障。
* `push2.eastmoney.com/api/qt/stock/get`：HTTP 200，返回 quote。
* `push2his.eastmoney.com/api/qt/stock/kline/get`：HTTP 200，返回 1 分钟 K 线。
* 东方财富隔离基准一轮：quote、1m、index 均 100% 成功；该结果仍只属于 `RESEARCH_ONLY`，未改变 Phase 2。

## 新的判定口径

| 来源 | quote | 日线 | 1m/5m | index | 当前定位 |
|---|---|---|---|---|---|
| Tencent | 可用 | 历史多次可用 | 旧 host 失败，备用 host 已恢复 | 未完整覆盖 | 按能力重测，非整体淘汰 |
| EastMoney direct | 本轮可用 | 待连续验证 | 本轮可用 | 本轮可用 | 隔离研究源 |
| AkShare | 本轮 RemoteDisconnected | 同上 | 同上 | 未完成 | 聚合 SDK，不计独立组 |
| FinShare | 部分可用 | 部分可用 | 未提供 | 未提供 | 未验证聚合源 |
| pytdx | 可用 | 可用 | 可用 | 可用但覆盖/新鲜度需观察 | 主要/热备候选 |
| Sina direct | 可用 | 不主供 | 1m 可用 | 可用 | 主要/热备候选 |
| BaoStock | 不主供 | 可用 | 5m 可用 | 非本目标主供 | 历史交叉验证源 |

## 已实施的低风险修复

1. 腾讯分钟线从失效的 `web.ifzq.gtimg.cn` 改为 `ifzq.gtimg.cn`，并添加请求头。
2. 能力矩阵新增 operation 级分类；quote 健康而 minute 失败时，quote 可标记 `ADAPT`，minute 单独 `REJECT`。
3. 保持 Phase 2、lineage、freshness、coverage、field completeness、cross-source consistency 门槛不变。

## 不应做的事

* 不把 AkShare、eFinance、东方财富直连计为多个独立来源。
* 不用一次成功直接把东方财富提升为生产主源。
* 不因单个域名 DNS 故障淘汰腾讯全部能力。
* 不用论坛标题、模型判断或旧缓存填补缺失的实时数据。

## 下一步

在至少 5 个交易时段记录 Tencent/EastMoney/Sina/TDX 的 quote、1m、index 同标的同轮数据，计算错误类型、延迟、时间戳年龄、字段完整性与 2% 一致性；只有连续达标后才评估角色升级。当前仍维持 `NOT_ADMITTED`，推票走老师审阅研究车道。
