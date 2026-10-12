# ACE 代码健康审计（2026-10-12）

> 审计对象：`zhangapple21-web/ace_core` @ `0143169`
> 审计方式：只读。`python -m compileall`、AST 静态分析、逐模块隔离导入探测、md5 与归一化行 Jaccard 重复检测。
> 复现命令：`python ops/code_health_audit.py`（本仓库新增的只读审计工具，不写任何状态）

---

## 0. 结论摘要

| 问题 | 等级 | 状态 |
|---|---|---|
| `core/__init__.py` 硬导入不存在的 `continue_gate_runtime` → 所有 `import core.*` 直接失败 | 🔴 致命 | 已复现 |
| `core/__init__.py:9` / `sitecustomize.py:7` 的 `parents[N]` 越界，实际把 `/` 插入 `sys.path` | 🟠 高 | 已复现 |
| 仓库完全没有依赖清单（无 requirements/pyproject/setup） | 🟠 高 | 已确认 |
| 生产运行时 `ace_daemon.py` 在干净环境无法导入（缺 `requests`） | 🟠 高 | 已复现 |
| `core/awareness_loop.py` 使用裸模块导入（非包导入）+ 双目录同名模块歧义 | 🟡 中 | 已确认 |
| `02_` / `03_` / `05_` 目录缺失；`08_` 编号被两个不同目录占用 | 🟡 中 | 已确认 |
| 12 组字节级完全重复文件（含 9 个 `core/` 与 `04_PROTOCOLS/` 同源副本） | 🟡 中 | 已确认 |
| `SyncResult` / `SyncPlan` 各在 3 处重复定义且字段不一致 | 🟡 中 | 已确认 |
| 134 处静默吞异常（118 处 `except Exception: pass`、16 处裸 `except:`） | 🔵 低 | 已确认 |

**没有发现的问题（同样是结论）：**

- `compileall` 通过，**0 个语法错误**（405 → 406 个 `.py`）。
- **0 个** 单文件内重复顶层定义，**0 个** 同类内重复方法名。
- **0 个** 无法解析的仓内 `core.*` / `ops.*` 导入。
- 测试资产真实存在：119 个 `ops/test_*.py`，739 个 `def test_*`。

---

## 1. 报错 / Bug

### 1.1 🔴 致命：`core/__init__.py` 硬导入不存在的模块

```python
# core/__init__.py:9-14
_shared_root = Path(__file__).resolve().parents[2]   # ← 越界，见 1.2
if str(_shared_root) not in sys.path:
    sys.path.insert(0, str(_shared_root))
import continue_gate_runtime                          # ← 无 try/except
continue_gate_runtime.install()
```

`continue_gate_runtime` 在本仓库中**不存在**（`core/continue_gate.py` 是另一个名字）。
而 `core/__init__.py` 是包初始化文件，因此**任何** `import core.*` 都会在这一行抛 `ModuleNotFoundError`。

实测三条路径全部失败：

```
$ python3 -c "import core.task"
  File "/workspace/core/__init__.py", line 12, in <module>
    import continue_gate_runtime
ModuleNotFoundError: No module named 'continue_gate_runtime'

$ python3 ace_start.py task X me
    from core.ace_start import ace_start
  File "/workspace/core/__init__.py", line 12, in <module>
ModuleNotFoundError: No module named 'continue_gate_runtime'

$ python3 -m core.continuity_audit
  File "/workspace/core/__init__.py", line 12, in <module>
ModuleNotFoundError: No module named 'continue_gate_runtime'
```

**根因判断（证据，非猜测）：**
`docs/CONTINUE_BEFORE_WORK_PROTOCOL.v1.md` 明确写：`Python 解释器通过用户级 sitecustomize.py 自动安装 continue_gate_runtime`。
也就是说该模块是**装机级（用户级 site-packages / 用户级 sitecustomize）注入的运行时依赖，从未进入本仓库**。

**后果：**
按 `NEW_COMPUTER_RESURRECTION.md` 的官方恢复路径（`git clone ace_core` 后直接运行），
新机器上**整个 ACE 运行时不可用**——不是某个功能坏掉，而是连模块都 import 不进来。
`README.md` 声称的“全量 pytest 744 passed”在原开发机上成立，是因为原机器装了该用户级模块；
本 checkout 无法复现。

**生产入口链因此整体是死的**（这是最实际的后果）：

```
ops/install_tasks.ps1:16-17   计划任务 → "ace.py" daemon --serve
  → ace.py:71-72              handle_daemon(...)
  → ace.py:381               from core.ace_start import run_runtime
  → core/__init__.py:12      import continue_gate_runtime   ← 在此处崩溃
```

即 Windows 计划任务注册的 `ace.py daemon --serve` 在干净 checkout 上无法启动，
`from core.ace_start import run_runtime` 就已经失败。


**反证：** 根目录 `sitecustomize.py` 对同一个导入**包了 try/except**，并注释说明“Never hide the original script error”。
说明“可降级”本就是设计意图，只有 `core/__init__.py` 漏了这层保护。

### 1.2 🟠 高：`parents[N]` 越界，把 `/` 插进 `sys.path`

```
$ python3 -c "from pathlib import Path; print(Path('/workspace/sitecustomize.py').resolve().parents[1])"
/
$ python3 -c "from pathlib import Path; print(Path('/workspace/core/__init__.py').resolve().parents[2])"
/
```

| 文件 | 行 | 现在 | 应为 |
|---|---|---|---|
| `core/__init__.py` | 9 | `parents[2]` → `/` | `parents[1]` → `/workspace` |
| `sitecustomize.py` | 7 | `parents[1]` → `/` | `parents[0]` → `/workspace` |

两个副作用：
1. 期望的“把工作区根加入 `sys.path`”**从未生效**——这正是 1.1 中 `continue_gate_runtime` 即使放在仓库根也找不到的原因。
2. 把文件系统根目录 `/` 前置进 `sys.path`，属于导入遮蔽（shadowing）与安全异味。

### 1.3 🟠 高：完全没有依赖清单

`requirements.txt` / `pyproject.toml` / `setup.py` / `Pipfile` / `setup.cfg` / `environment.yml` **全部不存在**（已全仓库搜索）。

生产代码实际使用的第三方依赖（无声明）：

| 依赖 | 影响面 |
|---|---|
| `requests` | 43 个模块导入失败，含 **`ace_daemon.py`（唯一生产运行时）**、`core/llm/client.py`、`core/miner_pool/*`、`core/provider_health_boundary.py`、`core/scheduler.py`、`core/task_queue.py` |
| `python-frontmatter` | 3 个模块 |
| `pytest` | 29 个测试文件 |
| `tkinter` | `core/companion/desktop_pet.py` |

干净环境下逐模块隔离导入探测结果：**308 成功 / 84 失败**，84 个失败中 **82 个是 `ModuleNotFoundError`**。

### 1.4 🟡 中：裸模块导入（非包导入）导致不可达 + 同名模块歧义

```python
# core/awareness_loop.py:40-42
from environment_sensor import EnvironmentSensor, SituationBuilder, Observation
from local_miner import call_model, health, list_capabilities, CAPABILITY_GRAPH
from roundtable import roundtable
```

这三个模块在 **`core/` 和 `04_PROTOCOLS/` 两个目录下同名存在且内容完全相同**。
于是“导入到哪一个”完全取决于运行时的 `sys.path` —— 行为不确定。
同时，作为 `core.awareness_loop` 导入时，`core/` 不在 `sys.path` 上，这三行必然 `ImportError`。

同类问题：

- `ops/run_autonomous_audit.py:3` → `from autonomous_audit import run_audit`（需 `ops/` 在路径上）
- `ops/reconcile_coordination_ledger.py:8`、`ops/test_coordination_ledger.py:2`、`ops/test_runtime_authority_audit.py:18`、`ops/test_active_work_manifest.py:3` → `from agent_team... import ...`
  但 **`agent_team/` 被 `.gitignore` 忽略且不存在** → `ImportError`

### 1.5 🔵 低：134 处静默吞异常

- 118 处 `except Exception: pass`
- 16 处裸 `except:`

分布含 `sitecustomize.py`、`core/heartbeat.py::_load` 等。
这与项目自身“fail-closed 而非 fail-silent”的治理原则相冲突：故障会被记录成“正常”，
可观测性受损。建议至少改为记录一条 receipt/日志。

### 1.6 🔵 低：配置指向不存在的路径 / 硬编码 Windows 路径

`ace_config.json` 引用以下路径，实际均不存在（虽在 `.gitignore` 中，但仓库内无任何 bootstrap 步骤创建它们）：

```
02_MEMORY  02_MEMORY/recent_memory  02_MEMORY/knowledge
06_RUNTIME/ace/data/{events,tasks,memory}
```

另有 `runtime.miner_pool_assets_path = "C:\\tmp\\private_coze-assets"` —— 硬编码 Windows 路径，在 Linux/macOS 上静默指向不存在的位置。


---

## 2. 项目完整性

### 2.1 代码本身是完整的

| 检查项 | 结果 |
|---|---|
| `.py` 文件数 | 406（含审计工具） |
| `compileall` | 通过，**0 语法错误** |
| 单文件内重复顶层定义 | **0** |
| 同类内重复方法名 | **0** |
| 仓内 `core.*` / `ops.*` 导入无法解析 | **0** |
| 测试文件 | 119 个 `ops/test_*.py` |
| 测试函数 | 739 个 `def test_*` |

> 注：`README.md` 与 `CURRENT_STATE.md` 均声称 “全量 pytest 744 passed”。
> 本 checkout 中 `pytest` 不可安装（沙箱无 PyPI 出口），该数字**无法复现**，
> 只能确认测试资产规模与之量级相符（739 个测试函数，参数化后可达 744 例）。

### 2.2 结构缺口

```
00_ROOT  01_CORE  [缺 02_ 03_]  04_PROTOCOLS  [缺 05_]  06_RUNTIME  07_SANDBOX
08_ARCHAEOLOGY
08_GOVERNANCE     ← 与 08_ARCHAEOLOGY 编号冲突
```

1. **`08_` 编号被两个语义完全不同的目录占用**（考古 vs 治理），违反 README 自述的“编号即层级”约定。
2. **`02_` / `03_` / `05_` 缺失**，但 README 与 AGENTS.md 的目录图仍在引用
   `02_MEMORY`（记忆层）、`03_DATA/CONSTRAINTS`（约束层）、`05_TOOLS`（工具层）。
3. `01_CORE/identity.json` 仅 **2 字节**（空对象），`01_CORE/` 无任何代码。
4. `06_RUNTIME/` 下只有 `workers/base_worker.py` 一个文件，且它是 `core/base_worker.py` 的完全副本。

### 2.3 文档与实现漂移（重要）

**(a) README 的“目录结构”整块已过期**
它描述的是 `ace.py + core/{identity,event_bus,task_queue,memory,scheduler} + nodes/{observer,researcher,validator,archivist} + data/`。
实际布局是 `ops/` + `08_GOVERNANCE/`，且 README 自己在开头就声明 `core/scheduler.py`、`core/task_queue.py` 已是 fail-closed legacy。

**(b) AGENTS.md 描述的“生产”模型网关其实没有消费者**
AGENTS.md 的 Model Strategy 写道：`Local Miner — Unified call_model() with auto-fallback, no TRAE dependency`。

实测：**`core/local_miner.py` 没有任何生产消费者**。

```
$ grep -rn 'local_miner' --include='*.py' core ops ace_daemon.py ace.py
core/awareness_loop.py:41:from local_miner import call_model, ...   ← AGENTS.md 自述 “historical, not wired”
core/roundtable.py:26:    from local_miner import call_github_models  ← 同样 “historical, not wired”
```

`ace_daemon.py` 完全不导入 `local_miner`；它走的是
`core.miner_pool.miner_pool.MinerPool` + `core.miner_pool.model_router.ModelRouter`。

也就是说文档中的“能力优先路由/本地矿工”描述的是一个**孤儿模块**，真正的生产模型路径是 `core/miner_pool/`。
这是文档漂移，而非崩溃，但会误导后续接手者。

**(c) AGENTS.md 只承认了 9 个重复模块中的 3 个**
AGENTS.md 提到 `environment_sensor.py` 副本、`recovery_protocol.py` 副本、RoundTable 重复实现；
但 `awaken / awareness_loop / civilization_map / environment_first / governor / local_miner` 这 6 个副本未被记录。

---

## 3. 重复文件

### 3.1 字节级完全重复（md5 相同）—— 共 12 组

**A. `04_PROTOCOLS/*.py` 与 `core/*.py` 同源副本（9 个文件，100% 相同）**

| `04_PROTOCOLS/` | `core/` |
|---|---|
| `awaken.py` | `core/awaken.py` |
| `awareness_loop.py` | `core/awareness_loop.py` |
| `civilization_map.py` | `core/civilization_map.py` |
| `environment_first.py` | `core/environment_first.py` |
| `environment_sensor.py` | `core/environment_sensor.py` |
| `governor.py` | `core/governor.py` |
| `local_miner.py` | `core/local_miner.py` |
| `recovery_protocol.py` | `core/recovery_protocol.py` |
| `roundtable.py` | `core/roundtable.py` |

**关键事实：`04_PROTOCOLS` 不是合法包名**（以数字开头），无法被 import：

```
$ python3 -c "import ast; ast.parse('import 04_PROTOCOLS')"
SyntaxError: invalid decimal literal
```

因此这 9 个副本**只能作为脚本直接执行**，无法通过导入到达；
而它们又给 1.4 的裸导入制造了同名歧义。

**B. 其余 3 组**

| 文件 A | 文件 B |
|---|---|
| `06_RUNTIME/workers/base_worker.py` | `core/base_worker.py` |
| `08_ARCHAEOLOGY/ops/runtime_fitness_report.md` | `08_ARCHAEOLOGY/ops/runtime_fitness_latest.md` |
| `08_ARCHAEOLOGY/binary_analysis_BlueStacksMicroInstaller_20260629_194939.md` | `08_ARCHAEOLOGY/binary_sense_reports/binary_analysis_BlueStacksMicroInstaller_20260629_194939.md` |

### 3.2 近似重复（归一化代码行 Jaccard ≥ 0.60）—— 共 10 对

即上述 A + B 的 `base_worker` 共 10 对，**Jaccard 全部为 1.000**。
除此之外**没有**任何其他近似重复对 —— 说明重复是“成组的显式副本”，不是散落的复制粘贴。


---

## 4. 可以合并 / 融合的

按“收益 ÷ 风险”排序。

### 4.1 ⭐ 首选：`04_PROTOCOLS/` 的 9 个副本 → 删除或降级为 fail-closed stub

**为什么低风险：仓库内已有现成先例。**
`04_PROTOCOLS/heartbeat.py` 全文只有 3 行，正是这个模式：

```python
"""Deprecated historical heartbeat boundary."""

raise RuntimeError("heartbeat_deprecated")
```

把其余 9 个文件套用同一模式即可：既保留“此处曾是 legacy 边界”的考古信息，
又消除 ~150KB 重复代码与同名导入歧义。

**前置条件（必须先确认，不要盲删）：**
这 9 个模块**没有任何 `core.*` 消费者**（已逐一验证，导入计数均为 0），
但**仍有文档引用它们**，且文档之间互相矛盾：

| 引用处 | 内容 |
|---|---|
| `NEW_COMPUTER_RESURRECTION.md:55` | 官方恢复步骤 `cd mine-seed` + `python 04_PROTOCOLS/awaken.py` |
| `00_ROOT/PRINCIPLES.md:706` | EFP 的实现被标注为 `04_PROTOCOLS/environment_first.py` |
| `README.md:7` / `research/runtime_authority_audit.v1.md:65` | 只把 `04_PROTOCOLS/heartbeat` 列为 fail-closed legacy |

也就是说：**`PRINCIPLES.md` 把 `04_PROTOCOLS/` 当作权威实现位置，
而实际可导入的权威位置是 `core/`** —— 这是“双权威位置”的文档冲突。

特别注意 `NEW_COMPUTER_RESURRECTION.md` 那一步是在 **`mine-seed` 仓库内**执行的
（`cd mine-seed`），说明 ace_core 里的 `04_PROTOCOLS/*.py` 很可能是 mine-seed 协议层的镜像副本，
为保留谱系而存在。因此：
1. 若要清理，应先确认 mine-seed 侧是否仍是权威源；
2. 同时修正 `PRINCIPLES.md:706` 的“实现”指向，否则清理后文档会指向不存在的文件。


### 4.2 `06_RUNTIME/workers/base_worker.py` → 保留 `core/base_worker.py`

两者字节相同。建议删副本，或在 `06_RUNTIME/workers/__init__.py` 中
`from core.base_worker import *` 做一次显式转发，避免两处实现漂移。

### 4.3 `SyncResult` / `SyncPlan` 三处重复定义（**需要字段决策，不是简单复制**）

```
SyncResult:
  core/sync_manager.py:41                 7 字段，无默认值，无 to_dict
  core/contracts/sync_contract.py:178     8 字段 + __post_init__（executed_at 自动填充）
  core/contracts/sync_execution_contract.py:132  10 字段 + to_dict（含 started_at/finished_at/operations_count）

SyncPlan:
  core/contracts/curator_decision_contract.py:419
  core/contracts/sync_contract.py:100
  （另有 SyncPlanVerification 在 core/contracts/sync_execution_contract.py:292）
```

三者**字段不一致**（`action: str` vs `action: SyncAction`，时间戳数量不同），
所以不能直接取其一覆盖。建议：
1. 在 `core/contracts/` 中定一个字段超集作为唯一契约；
2. `core/sync_manager.py` 改为从契约导入；
3. 先确认 `sync_contract.py` 与 `sync_execution_contract.py` 哪一份仍被引用
   （看起来是两代契约并存），再决定废弃哪一份。

### 4.4 测试辅助函数重复 → 并入已存在的 `ops/test_support.py`

`_git` / `_repo` 在 4 个文件中各自实现：

```
ops/test_remote_git_root_audit.py:7    def _git(...)  def _repo(tmp_path)
ops/test_remote_recovery_inventory.py:8 def _git(...)  def _repo(tmp_path)
ops/test_core_syncer.py:8               def _git(...)  def _repo()
ops/remote_git_root_audit.py:35         def _git(repo, ...)
```

`ops/test_support.py` 本来就是为共享 fixture 存在的，直接并入即可。

### 4.5 `ops/astra_30_case_evaluation.py`（148 行）与 `ops/astra_live_paired_evaluation.py`（154 行）

体量、目的、内部函数名（`run`、`_number`）高度一致，但 Jaccard 低于 0.60 阈值，
**不是**逐字副本。属“同一评测的两个变体”，可参数化合并为一个脚本
（`--mode 30-case | live-paired`）。合并前需确认两者输出 schema 是否要求一致。

### 4.6 文档归位

- 仓库根的 `archaeology_report_20260627.md` / `archaeology_report_20260628.md`
  与 `08_ARCHAEOLOGY/2026-06-27-ace.md` / `2026-06-28_*` 属同一族，根目录副本应归入 `08_ARCHAEOLOGY/`。
- `08_ARCHAEOLOGY/ops/runtime_fitness_report.md` 与 `runtime_fitness_latest.md` 完全相同：
  保留一份 + 由生成步骤产出 "latest"，或改成显式指针。

### 4.7 ⚠️ 明确**不建议**合并的（避免误伤）

| 项 | 原因 |
|---|---|
| `core/evidence_admission_compat.py` | 其 docstring 明确声明自己是 “Shadow-only compatibility and reporting” 的只读迁移层，并 `from .evidence_admission import ...`。这是**有意分层**，不是重复。 |
| `04_PROTOCOLS/heartbeat.py` | 已是正确的 fail-closed stub，无需处理。 |
| `core/governor.py` vs `core/governance/governor_protocol.py` | 体量 193 行 vs 1252 行，职责不同（前者是轻量门禁，后者是完整治理协议）；`core/governor.py` 的问题是它没有消费者（同 1.4/2.3b），属“归档”而非“合并”。 |
| 各 `ops/test_*.py` 之间的相似函数名（`_write`、`_record` 等） | 仅名字相同、实现不同，属正常测试局部辅助函数，不是重复。 |

---

## 5. 建议处理顺序

1. **先修 1.1 + 1.2**（两行代码）：给 `core/__init__.py` 的导入加 try/except 降级，
   并把 `parents[2]`→`parents[1]`、`parents[1]`→`parents[0]`。
   修完后 `import core.*` 与 `python ace_start.py` 才可能恢复。
   ⚠️ 注意 `continue_gate_runtime` 承载 continue-before-work 门禁语义，
   降级必须**显式记录 receipt**，不能静默跳过（否则违反 fail-closed 原则）。
2. **补依赖清单**：新增 `requirements.txt`（至少 `requests`、`python-frontmatter`、`pytest`），
   让 `ace_daemon.py` 在干净环境可导入。
3. **修 1.4 裸导入**：改为 `from core.environment_sensor import ...` 等包内绝对导入，
   同步消除双目录歧义。
4. **执行 4.1 / 4.2** 的副本清理（先确认无外部脚本调用）。
5. **处理 4.3 契约三重复**（需先做字段决策）。
6. 结构整理：`08_` 编号冲突、缺失的 `02_/03_/05_`、过期 README 目录图。
7. 1.5 的静默吞异常改为可观测记录。

---

## 6. 复现方式

```bash
# 只读审计（语法/重复定义/重复方法/导入解析/重复文件/近似重复/静默异常）
python ops/code_health_audit.py
python ops/code_health_audit.py --json > /tmp/audit.json

# 语法检查
python -m compileall -q . -x '(\.cline-home|\.git)'

# 1.1 复现
python -c "import core.task"

# 1.2 复现
python -c "from pathlib import Path; print(Path('/workspace/core/__init__.py').resolve().parents[2])"
```

> 本审计为只读观察，未修改任何源码、未触碰 TaskPool / 运行时状态 / 治理账本。
> 新增文件仅两个：`ops/code_health_audit.py`（审计工具，只读）与本报告。
> 上述结论均标注了可复现命令；未复现项（如 744 passed）已明确标为“无法复现”。

