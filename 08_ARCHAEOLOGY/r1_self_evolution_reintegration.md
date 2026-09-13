# R1 主动演化回接记录

日期：2026-09-13  
范围：`C:\tmp\R1`、`C:\tmp\ace_core`、`C:\tmp\r1-archaeology`、`C:\tmp\ACE原先备份` 及 `ace_core` 已配置的 Git 远端。

## 远程考古证据

- `mine-seed` 提交 `8886e00` 已有 QuestionEngine、ExplorerV2、Multi-Agent Debate、SelfEvolution、Heartbeat，语义链为 `Observation→Question→Debate→approved→SelfEvolution`。
- `r1-archaeology` 的 `PROTO-ACL-001`、`PROTO-DISCOVERY-001` 与 `PROTO-018 WORLD MERGE` 已定义主动探索、证据反证和验证→治理→追溯→合并。
- `ace_core` 远程 `main=0143169` 的 R1 边界文档确认：R1 现职责是代码/治理；自由区只能经桥接收据进入 Admission/Experience/Runtime，旧端口不应复活。
- `research/remote_civilization_map_20260912.json` 显示 `mine-seed`、`R1`、`r1-archaeology`、`r1-open-source-seed` 等仓库存在陈旧/Abandoned 演化缺口；多数本地 `.git` 对象损坏，不能把本地目录当作推送端。

以上材料只作为证据输入，不复用旧版“自动改代码→提交→推送”路径。

## 考古结论

R1 的历史材料已经包含三类能力：主动发现（扫描文件、仓库和外部信号）、跨域融合（按 subject/证据聚合）以及演化记录（演化报告、验证和回写）。`ace_core` 也已有这些零件，但运行时主要是“扫描器各自产出 → 一次性建任务”，没有稳定的“运行态瓶颈 + 历史材料 + 兄弟仓库活动 → 下一步验证”的统一入口。

## 本次回接

新增 `core/self_evolution.py` 的 `SelfEvolutionCoordinator`，并在 daemon 的生命周期中接入：

1. 主动采集运行态队列/错误、近期考古材料、兄弟 Git 仓库快照和已有远程文明地图；扫描有上限，Git 查询只读且有超时。
2. 按稳定主题做多来源融合，要求交叉证据或高置信单源，避免每个周期无条件造任务。
3. 生成带 fingerprint、来源、完成条件、验证方式和风险边界的提案，写入 `09_KNOWLEDGE/self_evolution/proposals.jsonl`。
4. 只写入现有 `RuntimeObserver` 的 `discovery_mode` Observation；后续继续走 `ObservationToTaskConverter → TaskPool → Validator/Guardian`，不新增执行权限。
5. 运行态状态写入 `06_RUNTIME/ace/data/self_evolution/state.json`，相同指纹保持幂等。

这样 R1 的“自我发现、自我融合”被接回现有治理链，主动演化仍然是可审计、可验证、可回滚的候选工作，而不是未经批准的自修改。

## 验证记录

- `py_compile`：`core/self_evolution.py`、`ace_daemon.py` 通过。
- 临时工作区 smoke test：两类独立证据生成 1 条 Observation，并被现有 Converter 转成 1 个 reasoning Task；第二轮同指纹返回 `ALREADY_ACTIVE`，未重复造任务。
