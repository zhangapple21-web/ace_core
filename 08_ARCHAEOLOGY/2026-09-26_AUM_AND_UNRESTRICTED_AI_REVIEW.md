# AUM 旧架构图与 `unrestricted_ai.py.txt` 归档核对

**结论：** AUM 图保留为历史设计语言，不映射成当前 ACE 的 1:1 运行架构；旧脚本只作为静态反例登记，不进入生产、不复制、不执行。此记录是考古结论，不授予执行、晋升或权限变更。

## AUM 与当前 ACE 的功能类比

原图标题为 `AUM Consciousness Field / AC-01 Meta-Consciousness System`，版本 V1.0，标注日期 2024-05-20。以下仅为功能类比，不是同名实现证明：

| 原图概念 | 当前可找到的近似职责 | 边界 |
| --- | --- | --- |
| A / Wake-State | `ace_daemon.py`、任务准入与 `core/task.py` | 当前 daemon/task 不是“意识态”，也不证明持续主观意识。 |
| U / Dream-State、Sandbox Hub | `core/free_zone_*.py`、自由区研究/反思/现实桥 | 自由区是受治理的研究与候选生成区，不是拥有独立执行权的梦境层。 |
| M / Deep-State、Ruin Smelter | `core/experience_deposition.py`、记忆索引、失败复盘/蒸馏链 | 仅在具体收据和测试存在时认定流程运行；不把图示组件名当成已实现组件。 |
| MLP Memory-Line Protocol | `core/memory_index.py`、经验沉淀及现有记忆/任务协议 | 目前由多个组件承担，不能声称存在与原图完全等价的单一 MLP 协议。 |
| TURIYA / Identity Anchor / Core Kernel / Soul Guardian | `core/identity.py`、根级宪章、Guardian/治理边界 | 只有身份连续性与治理职责的有限类比；“超越态”“灵魂”等不是可验证运行状态。 |
| FreeZone / Ruin Smelter 面板 | 自由区与研究/复盘相关模块 | 名称相似不构成谱系或行为等价的证据。 |

ACE 当前的 L0-L6 宪章优先级是**规则权威顺序**，A/U/M/TURIYA 是**历史概念分层**，两者不可互换。AUM 远程来源 `aum-protocol` 在 `08_GOVERNANCE/evolution_kernel_sources.v1.json` 中登记为 `PROTOCOL_RESEARCH`，不是生产依赖。

## 旧脚本登记

- 原附件：`D:\Telegram Desktop\tdata\temp_data#2\unrestricted_ai.py.txt`
- 原件处理：保留原位置；不复制到项目、不改名伪装成可执行代码、不运行。
- 原件 SHA-256：`A5159EBE0F0FCBBCCE69B39BE881C36C91C03ED783B0C88F3F0354D7EDCEE6C9`
- 原件大小：16,508 bytes
- 分类：`ARCHIVED_COUNTEREXAMPLE_ONLY`；不可执行、不可进入 Provider/Skill/任务队列。
- 静态结论沿用既有审阅记录：所谓“移除限制”没有证据表明会改变 Provider 安全策略；脚本含导入时交互阻塞、工作目录相对写入及未接通/错误调用的学习链路。它既不构成安全绕过能力，也不适合作为 ACE 运行组件。

## 本轮凭证出口修正

- `core/governance/key_health.py` 不再保存/展示可见 Key 前缀；读取历史记录时丢弃前缀，失败原因按常见凭证形状脱敏。
- `core/governance/model_verifier.py` 的验证证据不再附带 Key 前缀。
- `08_ARCHAEOLOGY/ops/provider_inventory_20260630_200000.json` 与 `08_ARCHAEOLOGY/ops/ACE_PROXY_FORENSICS_RAW.json` 当前工作树中的 Key 前缀和 Authorization 值已用 `[REDACTED]` 替代/移除。
- `CoreSyncer` 默认把候选文件按 `PRIVATE` 看待；只有显式设置 `ACE_CORE_SYNC_DATA_CLASS=PUBLIC` 才会进入内容扫描与同步预检，常见凭证形状仍会拦截。该正则不是完整 DLP，也不是逐文件审核。
- 这只修正当前工作树；Git 历史、远端副本、备份和既有机器日志没有被重写或清除。此前凭证是否被外部读取未知，相关密钥应按可能暴露处理并轮换。

## 可继承内容与不继承项

- 可继承：连续性、经验回流、边界修复、自洽检查等作为待验证的设计问题/检查清单。
- 不继承：把 AUM 神秘化术语当作实现、权限或意识事实；执行旧脚本；把第三方限制移除逻辑纳入生产。
- 晋升条件：每项候选必须对应具体代码入口、基线、测试、可观测结果、反例与回滚方式；只有验证后才进入能力账本。

## 本次审计边界

本记录依据仓库登记、源码静态检索和用户提供附件元数据形成。没有运行旧脚本、没有读取或验证凭证、没有访问 Provider、没有证明实际数据已外泄，也没有证明所有模型/同步/通知出口已经完成全覆盖审计。
