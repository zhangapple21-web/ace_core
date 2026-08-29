# ACE R1 / R2 博物馆考古与每日观察

## 目的

R1、R2 和旧的“24 小时学习”不是待复活的生产系统，而是可被重新检验的历史资产。本机制让自由区定期检查这些资产，回答四个可证伪的问题：

1. 这项机制真的留下过执行痕迹，还是只有脚本或叙事？
2. 它的安全语义是什么？
3. 当前 ACE 是否已经以更小、更安全的形式实现了它？
4. 如果还没有，是否值得形成一条仅供人工与治理审阅的提案？

## 运行边界

入口：

```text
ops/run_museum_archaeology_turn.py
    -> core/museum_archaeology_inventory.py
    -> 07_SANDBOX/free_research
    -> Curator / Court / Teacher queue
```

它只读取明确列出的本地历史路径和公开格式：日报 JSON、考古 Markdown、历史 Python 文件、历史影子审计记录。它不会扫描凭据、`.env`、Cookie、聊天内容、浏览器状态、私密 Telegram、生产配置或密钥。

它不会：

- 启动 R1/R2 的 daemon、heartbeat、scheduler、stock-advisor 或 Telegram；
- 创建第二个 ACE daemon；
- 修改 Runtime、TaskPool、Data Health、Advisor、Risk、Telegram、broker、Experience 或生产配置；
- 把历史荐股、历史评分或旧胜率当作现在的事实。

## 证据分级

| 标记 | 含义 |
| --- | --- |
| `RUNNING` | 仅在当前受控运行态可证明；本轮历史考古不会因文件存在而标记它。 |
| `HISTORICAL_EXECUTED` | 有带日期、结构或日志的历史产物，证明当时有报告/观察活动。 |
| `CODE_ONLY` | 有代码，但没有足够的本地执行证据。 |
| `DESIGN_ONLY` | 只有设计、宣言或架构叙事。 |
| `DUPLICATE` | 当前安全机制已经覆盖其核心语义。 |
| `SUPERSEDED` | 已被历史归档明确替代；只保留血缘价值。 |

执行证据证明的是“当时存在某种活动”，并不证明旧代码就是产物的唯一来源，更不证明其中结论现在仍然成立。

## 处置规则

| 处置 | 允许的行为 |
| --- | --- |
| `ABSORB` | 把明确、安全、可复核的语义作为自由区实验输入。 |
| `ADAPT` | 只复用语义，重新设计受控实现。 |
| `CONFLICT` | 保存为反例或局部启发，禁止直接接入。 |
| `REDUNDANT` | 记录血缘，不重复造已有能力。 |
| `REJECT` | 作为负面案例保留，禁止复活。 |

## 本轮已验证的历史价值

- `private_claw-soul` 有一段连续的结构化日报系列，证明 R2 真实做过“观察—经验—信号—决策—日报”的节律。
- `r1-archaeology` 留存多日考古报告，证明“发现 + 矛盾 + 下一问题”是可持续的工作形态。
- 旧 `daily_self_loop.py`、`heartbeat.py`、`autonomous_loop.py` 是代码资产，不等于当前运行能力；其中包含自动荐股、自动触发、进程启动或外发路径，不能进入当前唯一 daemon。
- R2 的启动死锁取证是一条要保留的反证：单一中枢排他循环没有逃生通道会让系统自锁。

## 当前可沉淀的最小语义

自由区可每日做一件小事：从有真实证据的历史材料中选一个尚未消费的机制或失败，登记为 `FREE_RESEARCH_ONLY` 实验；馆长只蒸馏干净的 `PASS`，法院校验来源，老师只看到人工审阅队列。没有变化时明确写 `NO_NEW_MUSEUM_WORK`。

这实现了“每天走路”，但不把活动数量伪装成进步。
