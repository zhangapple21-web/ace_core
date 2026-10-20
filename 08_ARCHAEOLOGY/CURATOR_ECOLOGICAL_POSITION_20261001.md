# 馆长生态位置考古补录

## 证据来源

- `2026-06-28_R1认知路由协议考古报告.md`：馆长由资料馆管理员深化为系统级观察者、规则层修改者、冲突驱动进化者。
- `archaeology_report_20260628.md`：馆长出现后，系统重点从回答问题转为维护知识文明；馆长不是普通档案管理员。
- 同一报告第十九节：Knowledge Governor 负责“有没有资格进入文明”，Repository Governor 负责“应该去哪”。
- `2026-07-02_r1_chip_evolution_archaeology.md`：观察层由 Observer、Repository Curator、Governor 共同构成。

## 定位

馆长是持续存在于生态中的观察位置，不是某个输入的处理器，也不是 daemon 每轮工作流中的普通节点。

馆长观察：

- 系统全局状态、知识结构和长期趋势；
- 新旧知识之间的重复、冲突、断裂和修订压力；
- 仓库边界、文明目录和同步决策的长期一致性；
- 哪些问题需要规则层调整或触发后续治理。

馆长不替代：

- Researcher 的发现；
- Validator/Guardian 的证据与安全裁决；
- Mengpo 的遗忘执行；
- TaskPool 的任务权威；
- Knowledge Governor 的文明准入判断。

## 当前继承

`core.repository_curator.RepositoryCurator` 继承的是馆长的 Repository Governor 侧：维护仓库判断、相似度、价值评分、归档/合并/拆分建议和同步计划权限。

当前 daemon 只调用 `observe_ecosystem()` 记录持续观察快照，不把馆长作为本轮产物处理节点。显式 `wakeup()` 仍保留为受治理的仓库决策入口，不由普通工作流自动赋予新的生产权限。

## 证据等级

- 历史人格与生态定位：`HISTORICAL_EXECUTED` / `ARCHAEOLOGY_BACKED`
- 当前代码继承与权限：`IMPLEMENTED`
- 自主规则改写与冲突驱动演化：未证明，不得宣称已实现

## 不变量

馆长观察记录不等于能力晋升，不等于 Guardian 批准，不等于同步执行。所有仓库变更仍须经过既有权限、契约、签名和同步边界。 
