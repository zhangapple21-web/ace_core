# ACE 因子与微观结构研究候选裁决

更新时间：2026-08-31  
状态：`RESEARCH_ONLY`；只读考古和设计裁决，不安装、不克隆、不接入生产。

## 1. 结论先行

最适合 ACE 的不是引入一个“自动赚钱模型”，而是建立一个隔离的因子实验室：

```text
自由区提出假设/随机生成
        ↓
不可变评估器（固定数据、固定规则、固定成本）
        ↓
多目标前沿（预测力、稳定性、可交易性、复杂度）
        ↓
Alphalens 式衰减/分层/换手分析
        ↓
Walk-forward + 样本外 + 反例挑战
        ↓
老师审阅研究简报（仍不自动荐股）
```

核心原则是“多样性和可复现性优先于单一最高分”。一个 IC 略低但稳定、低换手、结构简单的因子，可能比一次回测最高分的复杂因子更值得继续研究；这只是研究优先级，不是收益承诺。

## 2. 外部线索逐项裁决

| 线索 | 裁决 | 只吸收什么 | 不能吸收什么 |
| --- | --- | --- | --- |
| NSGA-II 多目标遗传规划 | `ADAPT-CANDIDATE` | 将 RankIC、IC 胜率/IR、Top-k 排序质量、换手/成本、复杂度作为并列目标；保留 Pareto 前沿 | 不把论文或券商宣传的“高胜率”当作事实；不直接生成生产规则 |
| `nshen7/alpha-gfn` | `RESEARCH` | GFlowNet 的随机、多样化公式探索；奖励函数可加入缺失率和复杂度惩罚 | 官方 README 明确是演示项目，数据为日频技术数据且示例偏美国市场；不能证明 A 股早盘或 L2 有效 |
| `QuantaAlpha/QuantaAlpha` | `RESEARCH`（抽屉已有） | 研究方向→假设→代码→回测的轨迹记录、因子血缘、结构化进化 | README 的跨市场结果需要独立复现；不允许 LLM 直接越过数据门或输出荐股 |
| `1998x-stack/alpha-autoresearch` | `ADAPT-CANDIDATE` | `prepare.py` 只读、`factors.py` 单一编辑面、RankIC/IR/Turnover 三目标 Pareto、简单性偏置、失败可留存 | 其 2020–2025、495 股票示例数据的来源/点时完整性尚未由 ACE 验证；不安装或执行外部代码 |
| Level-2 波动分解 | `RESEARCH` | 将连续波动与跳跃波动作为可检验的微观结构假设 | 当前 ACE 没有已准入、可独立交叉验证的 L2 源；没有合法来源、覆盖、时间戳和成本证明前拒绝生产化 |
| 订单失衡/撤单行为 | `RESEARCH` | 作为开盘阶段行为假设，要求逐笔快照和盘口深度的冻结回放 | 不能把“机构持续调仓”“散户跟风”等叙述直接映射为标签；撤单数据需检查样本偏差和可操纵性 |
| GRU/Transformer 时频因子 | `DEFER` | 仅在简单基线失败且样本量足够后，作为对照模型 | 黑箱模型、单次 RankIC 或训练集结果不能进入老师简报；不得替代可解释规则 |
| 资金流因子 | `ADAPT` | 把资金流作为辅助上下文，并记录来源、时间戳、独立组和缺失 | 腾讯/东方财富/聚合 SDK 同一上游不能计作多个独立来源；资金流不能单独触发候选 |
| 大小盘风格拥挤度 | `ABSORB-CANDIDATE` | 用微盘/沪深300相对动量、成交额比率的滚动分位数做市场状态过滤 | 不把任意 10/20/60 日阈值当作已验证参数；指数源不稳定时不得计算实时结论 |
| Quant Wiki / 二手研报合集 | `RESEARCH_ONLY` | 用于发现原始论文、变量定义和复现线索 | 二手文章不是独立证据源，不能直接进入 lineage 或胜率统计 |
| `microsoft/qlib` | `ADAPT`（抽屉已有） | 数据集/特征/实验版本化、离线回放组织 | 不引入第二套生产 Scheduler、Gateway 或交易执行链 |
| `stefan-jansen/alphalens-reloaded` | `ABSORB`（抽屉已有） | IC、分层收益、换手、衰减、样本外报告结构 | 不把因子分析结果当作当前行情或荐股资格 |
| `vnpy/vnpy` Alpha | `ADAPT`（抽屉已有） | 因子表达式和离线研究组织 | 明确拒绝 Gateway、券商、订单和实盘模块 |

## 3. 与 ACE 现有能力的对齐

### 已经具备、无需另起炉灶

- `core/early_session_research_protocol.py`：盘前到 09:45 的时间切片和硬数据门；
- `core/market_context_research.py`：指数、板块和市场状态上下文；
- `core/financial_technical_features.py`：基础技术特征；
- `core/teacher_review_packet.py` / `core/daily_research_brief.py`：候选卡和老师审阅输出；
- `07_SANDBOX/free_research`：隔离实验、蒸馏和失败留存；
- `08_GOVERNANCE`：证据、知识生命周期和外部项目目录。

### 建议的唯一新增研究能力

在现有自由区里增加一个“因子实验契约”（设计候选，不立即编码）：

```text
factor_id / parent_ids / formula_ast / feature_sources
dataset_snapshot_hash / point_in_time_rule / universe_rule
cost_model / embargo_window / random_seed / code_hash
metrics: RankIC, IC_IR, hit_rate, NDCG@k, turnover, drawdown_proxy
pareto_status / complexity / missingness / cross_source_consistency
out_of_sample_split / counterexamples / teacher_decision
```

它应复用现有 `FreeResearchSandbox`、证据注册和老师审阅链，不能建立第二个 TaskPool、Scheduler、Router 或生产数据适配器。

## 4. 语义切片与随机概率如何使用

“随机”只用于自由区探索，不用于绕过证据门：

1. 每个实验保存 `random_seed`、候选生成分布和父因子血缘；
2. 以市场状态切片（趋势、震荡、退潮）、行业切片、流动性切片和交易时段切片分别评估；
3. 报告总体结果与最差切片，防止一个行情阶段掩盖失效；
4. 随机探索保留 `PASS`、`FAIL`、`INCONCLUSIVE`，失败是研究产出，不得自动晋级；
5. 只有通过样本外、反例挑战和 ACE 当前数据准入的结果，才有资格进入老师审阅候选。

## 5. 数据与生产边界

当前 A 股 `quote / minute_kline_1m / index` 的 Phase 2 仍未严格准入。腾讯、东方财富、Sina、pytdx、BaoStock 的能力必须按 operation 记录，不能因为一个端点成功就整体升级。L2 研究还额外需要：

- 合法且可持续的账户/授权；
- 逐笔或盘口字段的明确 lineage；
- 多标的、多交易日、多时段覆盖；
- 至少一个独立来源的时间戳和一致性对照；
- 延迟、丢包、撤单、复权和交易成本的记录。

在这些条件满足前，L2、订单失衡、GRU/Transformer 都只能是研究假设；不能补齐实时数据、不能改变 Data Health/Admission、不能打开 Advisor/Risk/TG。

## 6. 推荐顺序

1. **P0：** 先用现有历史数据做一个不可变的因子评估契约，复用 Alphalens/Qlib 的报告思想；
2. **P1：** 将 `alpha-autoresearch` 的 Pareto、单一编辑面、简单性偏置作为自由区实验模板候选；
3. **P1：** 将风格拥挤度做成市场状态研究变量，不作为独立荐股信号；
4. **P2：** 在获得合法 L2 数据后，再研究波动分解和订单失衡；
5. **P3：** 最后才比较 GFlowNet、LLM 进化和深度模型，且必须与简单基线做盲测。

## 7. 明确不做

- 不安装或运行上述外部仓库；
- 不把 GitHub Star、README 结果或二手研报写成 ACE 的收益证明；
- 不把论坛情绪、资金流或模型生成的解释当作 quote/1m/index 的替代；
- 不因为“系统要成长”而降低 lineage、freshness、coverage、field completeness 或 cross-source consistency；
- 不自动荐股、下单、发 Telegram 或承诺客户收益。

## 8. 本轮已执行的最小实现

已新增纯研究模块 `core/factor_experiment_contract.py` 及
`ops/test_factor_experiment_contract.py`：

- 强制记录公式/父因子、特征来源、数据快照哈希、点时规则、成本模型、随机种子、代码哈希、语义切片、样本外划分和反例；
- 对 RankIC、IC_IR、NDCG@k、换手、复杂度、缺失率执行有限值校验；
- 提供确定性的 Pareto 支配和前沿计算，明确高预测力与低成本/低复杂度之间的权衡；
- 固定 `mode=FACTOR_RESEARCH_ONLY`、`production_integration=false`、`recommendation_authority=false`；
- 模块不读取行情、不调用模型、不写 TaskPool/Advisor/Risk/Telegram，后续可由现有 FreeResearchSandbox 保存记录。

这只是“可验证记录契约”，不是因子生成器、回测引擎或自动荐股器；任何真实因子仍需由现有自由区和 ACE 证据链单独验证。

## 外部核验记录

- [alpha-gfn GitHub](https://github.com/nshen7/alpha-gfn)：README 明确说明为演示项目，示例使用日频技术数据。
- [QuantaAlpha GitHub](https://github.com/QuantaAlpha/QuantaAlpha)：README 描述 LLM+进化轨迹，需要独立复现其结果。
- [alpha-autoresearch GitHub](https://github.com/1998x-stack/alpha-autoresearch)：README 描述 3 个 Pareto 指标、不可变评估器和单一编辑面。
- [Qlib GitHub](https://github.com/microsoft/qlib)：作为 ACE 已有研究候选，不改变生产边界。
- [Alphalens Reloaded GitHub](https://github.com/stefan-jansen/alphalens-reloaded)：作为 ACE 已有因子分析候选。
