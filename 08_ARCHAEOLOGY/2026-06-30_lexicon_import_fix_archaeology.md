# 结构修复考古报告：core.lexicon 导入冲突修复

**日期**: 2026-06-30
**修复类型**: 结构断裂修复
**严重程度**: 致命（主循环无法启动）
**修复状态**: 已修复

---

## 一、问题描述

### 现象
执行 `python ace_daemon.py` 时抛出：
```
ImportError: cannot import name 'Lexicon' from 'core.lexicon'
```

### 根因
`core/` 目录下同时存在：
- `core/lexicon.py` — 旧版词库主模块，包含 `Lexicon` 类
- `core/lexicon/` — 新版词库分类体系包（目录），包含 `lexicon_categories.py`

Python 导入规则：**包（目录）优先于同名模块（.py 文件）**。

当代码执行 `from core.lexicon import Lexicon` 时，Python 解析到的是 `core/lexicon/__init__.py`，而该文件中只导出了分类体系相关内容，没有 `Lexicon` 类。

### 影响范围
以下 5 个文件依赖 `from core.lexicon import Lexicon`：
1. `core/scheduler.py` — 调度器核心
2. `core/memory_index.py` — 记忆索引
3. `core/disk_scanner.py` — 磁盘扫描器
4. `core/binary_sense/binary_sensor.py` — 二进制感知
5. 间接影响：所有依赖上述模块的组件（主循环全部）

---

## 二、演化关系分析

### 结构血缘
这是一个典型的**模块演化中的命名过渡问题**：

```
旧结构（单体）
    core/lexicon.py  ← 所有词库逻辑都在这里
        ↓
    演化分裂
        ↓
新结构（分层）
    core/lexicon/          ← 新的分类体系包
        __init__.py
        lexicon_categories.py
    core/lexicon.py        ← 旧的主模块还在这里，未迁移
```

### 约束沉积
从代码结构可以推断：
1. **分类体系先独立出来** — `lexicon_categories.py` 是新抽取出的子模块
2. **主模块迁移未完成** — `Lexicon` 类还在 `lexicon.py` 中，没有移入包内
3. **`core/__init__.py` 已更新** — 只从包中导入分类相关内容，说明包是"新正统"
4. **下游导入未同步更新** — `scheduler.py` 等仍在导入 `Lexicon`

这属于**结构演化中的中间状态** — 新结构已经建立，但旧结构还未完全迁移，导致断裂。

---

## 三、修复方案

### 修复原则
- 最小侵入：不修改 `lexicon.py` 和下游 5 个文件
- 向后兼容：保持 `from core.lexicon import Lexicon` 可用
- 平滑过渡：为后续完整迁移留有余地

### 修复位置
`core/lexicon/__init__.py` — 新包的入口，在这里兼容旧模块的导出。

### 修复内容
1. 检测 `core/lexicon.py` 是否存在（过渡时期存在）
2. 将 `core.identity` 注册为 `core.lexicon.identity`（解决相对导入问题）
3. 从文件加载 `lexicon.py` 的内容到当前包命名空间
4. 将 `Lexicon` 类加入 `__all__` 导出列表

### 为什么选择这个方案
- **不修改下游代码**：5 个文件的导入语句保持不变
- **不移动 Lexicon 类**：避免大规模重构引入新问题
- **在包入口做兼容**：这是最自然的"过渡层"位置
- **可检测可回退**：如果 `lexicon.py` 不存在就跳过，不影响纯包模式

---

## 四、验证结果

### 导入验证
```
from core.lexicon import Lexicon  → 成功
from core.scheduler import Scheduler  → 成功
```

### 主循环验证
`ace_daemon.py` 完整运行成功，关键指标：
- 词库概念: 1313 → 1314（+1）
- 记忆索引: 102 → 156（+54）
- 任务池: 129 → 133（+4）
- 今日考古摘要: 已生成（ID: 6a7f9e81）

---

## 五、后续演化建议

### 短期（过渡状态）
当前修复方案可正常运行，属于"搭桥"性质。

### 中期（结构整合）
建议将 `Lexicon` 类完整移入 `core/lexicon/` 包内，例如：
- `core/lexicon/lexicon.py` — 词库主类
- `core/lexicon/lexicon_categories.py` — 分类体系
- `core/lexicon/__init__.py` — 统一导出

### 长期（完全迁移）
完成迁移后删除旧的 `core/lexicon.py` 文件，彻底结束过渡状态。

---

## 六、教训与经验沉积

### 教训
1. **模块演化不能半吊子** — 要么全迁要么别动，中间状态最容易出问题
2. **包与模块不同名** — 这是 Python 的基本约束，演化时必须遵守
3. **先改下游还是先改上游？** — 应该先建好新结构的兼容层，再逐步迁移下游

### 经验
- **结构断裂的修复优先级最高** — 系统连启动都做不到，其他都是空谈
- **过渡层放在新结构入口最合理** — 就像旧城改造，先铺好新路再拆老房子
- **最小侵入原则** — 能在一个点修复的，不要扩散到多个文件

---

*修复人: ACE 自动考古主循环执行代理*
*修复时间: 2026-06-30 18:45*
