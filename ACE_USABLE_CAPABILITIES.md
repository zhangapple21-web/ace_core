# ACE 可用能力总表

这是 ACE 主线唯一的“可用能力入口”。以后判断某项成果能不能直接用于 ACE，先看这张表；其他窗口的记忆、实验报告、队列卡和镜像都只能作为证据或历史材料，不能替代这里的状态。

## 状态口径

- **主线可用**：代码在 `ace_core`，有可重复命令和回归测试；可以从这里调用。
- **主线已有**：代码在 `ace_core`，但只在已有调用者/测试范围内成立，不代表已经接入所有运行路径。
- **候选未切换**：已经有实现和证据，但生产运行仍使用旧路径；不能当作已启用。
- **待修/不纳入**：发现的问题或实验材料，先留在队列/证据仓，不复制进主线。

## 现在可以直接用的能力

| 能力 | 状态 | 主线入口 | 复算命令 | 当前边界 |
|---|---|---|---|---|
| 任务胶囊、回程端口、恢复和只读回看 | **主线可用** | `core/worker_capsule.py`、`ops/worker_capsule_cli.py` | `PYTHONIOENCODING=utf-8 py -3.11 -m pytest ops/test_worker_capsule.py ops/test_worker_capsule_cli.py -q` | 目前是显式 CLI/演练入口；F01/F02/F08 等接入与异质执行环境问题仍未全部关闭，不能宣称 daemon 已默认使用它 |
| 跨进程死亡恢复演练 | **主线可用** | `ops/worker_capsule_death_drill.py` | `PYTHONIOENCODING=utf-8 py -3.11 -m ops.worker_capsule_death_drill first` | 演练和生产只读探针已留证；它证明恢复面，不等于所有 worker 都已迁移 |
| 证据准入与重复候选判定 | **主线已有** | `core/evidence_admission.py`、`core/evidence_admission_compat.py`、`core/task_admission.py`、`core/beneficiary_check.py` | `PYTHONIOENCODING=utf-8 py -3.11 -m pytest ops/test_evidence_admission.py ops/test_evidence_admission_compat.py ops/test_beneficiary_check.py -q` | 只按现有调用者和测试使用；不要把 registry 中的独立 `ACE-CAP-evidence-admission` 包当作另一套生产实现 |
| 因子回放与 walk-forward 校验 | **主线已有** | `core/factor_replay.py` | `PYTHONIOENCODING=utf-8 py -3.11 -m pytest ops/test_research_adapters_and_replay.py -q` | registry 中的 `ace_factor_replay` 是抽取/兼容证明材料，尚未成为主线第二套入口 |

## 有价值但暂不切换的能力

| 能力 | 状态 | 现在的唯一正本 | 为什么不直接启用 |
|---|---|---|---|
| Memory Kernel / Hindsight 风格检索 | **候选未切换** | `core/memory_index.py` 仍是 daemon/worker 的实际读写面；`core/memory_kernel.py`、`core/memory_gateway.py` 是迁移候选 | 主线 AGENTS 已明确 caller unification 未达成；切换前必须完成一次性迁移闸、回滚闸和自然 daemon 验证，不能因为文件存在就称为生产记忆 |
| `ace_capability_registry` 的抽取包、登记尺和大量窗口审计件 | **证据/候选** | `C:\轻量项目\ace_capability_registry` | 这些东西提高可追溯性，但没有自动获得 ACE 生产调用权；只有明确验收、复制引用和主线复算完成后，才可进入本表的“主线已有” |

## 明确不纳入主线的内容

以下内容继续保留在各自证据仓，不复制、不伪装成可用能力：

- Qwen F01–F05、F08 队列卡中尚未关闭的接入/池闸/重复键/异质执行环境问题；
- 只有记忆、自述或桌面报告，没有主线文件、测试和回执三件套的成果；
- 只改审计尺、计数口径或卡片正文，未改变 ACE 运行行为的治理材料；
- registry 的 `CANDIDATE` 包、临时探针、会话目录脚本和未进版本层的回执。

## 固化规则

1. 新成果只能先登记在本文件，必须写清主线入口、复算命令、边界和验收状态。
2. 只有“主线可用/主线已有”才允许被其他 ACE 代码或任务说明引用。
3. “候选未切换”只能通过现有迁移/验收路径推进，不能另起一套 daemon、memory index、TaskPool 或能力入口。
4. 任何状态升级都必须带主线提交号、可重跑命令和 focused regression；没有这三项，状态保持不变。

最后复核：2026-09-29（Asia/Shanghai）。
