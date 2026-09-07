# ACE 决策纪律固化（v1）

更新时间：2026-09-07（Asia/Shanghai）  
状态：`RESEARCH_ONLY`

## 总原则

> **先看事实，再看结构；再看位置、价格与预期。确认后敢做，失效后敢退；没有赔率不做，指标只作借鉴，不替我们下判断。**

ACE 已把这句话固化为 `core/decision_discipline.py` 的 `ace.decision_discipline.v1` 契约。它不是新因子，不是收益模型，也不是把段永平或 TN6 变成自动信号；它是候选卡、分类器和复盘共用的检查顺序。

股票即时问答入口也复用同一个 `ace.stock_chat_decision_protocol.v1` 文本契约。这样用户在问“怎么看/推几只/能不能提前看出”时，聊天层不会另起一套话术，而是沿用同一条事实→结构→位置/价格/预期→确认→失效→赔率链。公司/行业交易逻辑、为什么现在、价格是否仍有赔率和 1–2 日时间窗口作为解释上下文接入，不参与打分，也不绕过数据准入。

## 接入边界

1. `facts`、`structure`、`position_price_expectation`、`confirmation`、`invalidation` 和 `odds` 必须分开记录，不能用一句“看起来很强”代替。
2. `odds` 为空时，记录状态为 `NO_ODDS_DO_NOT_ACT`；即使机会分数是 A/A+，执行端点也不能进入执行，只能等待补齐赔率或确认。
3. 纪律对象的 `score_contribution` 固定为 `0.0`，不改变 `attack_grade`、`conviction`、`risk_level`；高风险仍可保留 A/A+，但要缩短验证窗口、按失效退出。
4. TN6 和其他指标固定为 `context_only`。100 个指标码能提供结构问题和反方问题；没有公式文本、点时回放和样本外证据，就不能替我们下判断。
5. 现有日级诚实输出继续有效：最高只有 B 时输出 `NO_A_TODAY`，没有候选时输出 `NO_SUITABLE_SETUP`，不为了“推两支”凑数。

## 固化后的运行顺序

```text
事实
  → 结构
  → 位置 / 价格 / 预期
  → 确认
  → 失效 / 退出
  → 赔率
  → 进入 1–2 日验证，或停在 NO_ODDS_DO_NOT_ACT / RESEARCH_ONLY
```

这条契约只提供可审计的判断骨架；真实候选仍必须经过当前行情、板块联动、量价、资金连续性、数据新鲜度、独立来源和历史回放。缺证据时保留 `UNKNOWN` 或 `RESEARCH_ONLY`，不补写事实。
