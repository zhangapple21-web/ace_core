# ACE Runtime 核心记忆

本文件记录系统关键架构决策和同步规则。

---

## 一、仓库结构

| 仓库 | 用途 | 位置 |
|------|------|------|
| mine-seed | 考古产物（词库、记忆、报告、数据） | `03_DATA/research/r1_archaeology` |
| ace_core | 核心源代码（Python） | `ace_runtime/` 本地 git 仓库 |

两个仓库完全独立，互不包含。

---

## 二、ace_core 仓库

### 仓库信息

- **Remote 名称**: `ace-core`
- **Remote URL**: `https://github.com/zhangapple21-web/ace_core.git`
- **仓库已创建**: 2026-06-28
- **分支**: `main`
- **本地路径**: `ace_runtime/` 根目录

### 追踪范围

```
ace_runtime/
├── ace_daemon.py          ✅ 主入口
├── core/                  ✅ 所有核心模块
│   ├── task.py
│   ├── task_roles.py
│   ├── task_creator.py
│   ├── fragment_index.py
│   ├── file_scanner.py
│   ├── core_syncer.py
│   └── ...
├── 06_RUNTIME/workers/   ✅ Worker 实现
└── 08_ARCHAEOLOGY/       ✅ 仅 .py 考古脚本（无 .md 报告）
```

### 忽略范围

- 所有 `.json`、`.zip`、`.md` 报告文件（考古产物放 mine-seed）
- `task_pool/`、`02_*` 数据目录
- `08_EVENTS/`、`09_KNOWLEDGE/`
- `06_RUNTIME/ace/`（数据目录）

详见 `.gitignore`。

---

## 三、同步规则（CoreSyncer）

### 推送时机

- 每次 `ace_daemon` 主循环结束时检查
- 推送条件：核心代码目录有 `.py` 文件变更
- 防抖：距离上次推送 **< 60 分钟** 不推送（除非 `force=True`）

### 防抖理由

不要因为每次小变更就触发推送。积累一批变更再推送，降低 GitHub API 消耗，同时避免刷屏提交历史。

### 触发链路

```
ace_daemon.run_once()
  → _run_task_lifecycle()
    → Archivist.archive_task() → Task archived
  → _run_autonomous_loop() → 任务全部处理完毕
  → CoreSyncer.sync() → 检查变更 → 满足则 push
  → mine-seed sync（独立）
```

---

## 四、Repository Curator（仓库馆长）

### 架构角色

```
Observer        → 持续观察，记录 Observation
      ↓
Researcher      → 生产知识（考古报告、经验、协议）
      ↓
Validator       → 验证任务结果
      ↓
Archivist       → 归档到本地目录
      ↓
Repository Curator  → 馆长整理（唯一有权决定同步的 Agent）
      ↓
Sync Manager    → 执行馆长的同步指令
      ↓
Git Push        → 写入仓库
```

### 权限矩阵

| Agent | create | modify | code | sync | git_push |
|-------|--------|--------|------|------|----------|
| Research Agent | ✅ | ✅ | - | ❌ | ❌ |
| Engineering Agent | - | ✅ | ✅ | ❌ | ❌ |
| Repository Curator | ✅ | ✅ | ✅ | ✅ | ✅ |

**关键约束**：所有 Agent 的产出必须经过馆长，馆长是 Git 的唯一入口。

### 馆长工作流程

```
Today's Work Finished
      ↓
Repository Curator Wakeup（触发方式：scheduled / task_complete / manual）
      ↓
Collect Today's Artifacts（扫描 ace_runtime 产物目录）
      ↓
Score Each Artifact（Novelty / Similarity / Stability / Reusability）
      ↓
Find Similar Docs（n-gram Jaccard 相似度检测）
      ↓
Decide Action（create / update / merge / discard / split）
      ↓
Generate Sync Plan（含馆长签名）
      ↓
Sync Manager Execute（防抖 + 签名验证）
      ↓
Archive + Log
      ↓
Sleep
```

### 核心文件

- `core/similarity_engine.py` — n-gram Jaccard 相似度引擎（无外部依赖）
- `core/value_scorer.py` — 价值评分器（4维度评分）
- `core/repository_curator.py` — 馆长主体逻辑
- `core/sync_manager.py` — 同步执行器（仅执行馆长指令）
- `ops/curator_validate.py` — 馆长验证脚本

### 手动强制推送

```bash
cd ace_runtime
python -c "
from core.core_syncer import CoreSyncer
syncer = CoreSyncer(repo_path='.', remote='ace-core')
result = syncer.sync(force=True)
print(result)
"
```

---

## 四、待完成项

### ⚠️ 创建 ace_core GitHub 仓库

用户需要手动完成：

1. 登录 GitHub，创建新仓库 `ace_core`（不要初始化 README 或 .gitignore）
2. 获取仓库 URL
3. 更新本地 remote：

```bash
cd ace_runtime
git remote set-url ace-core https://github.com/YOUR_USERNAME/ace_core.git
git push -u ace-core master
```

---

## 五、架构决策记录

| 日期 | 决策 | 理由 |
|------|------|------|
| 2026-06-27 | ace_core 与 mine-seed 分离 | 考古数据 vs 源代码，演进速率不同 |
| 2026-06-27 | CoreSyncer 防抖 60 分钟 | 避免频繁小推送，保持提交历史整洁 |
| 2026-06-27 | 仅推送 .py 文件 | .md 报告归属 mine-seed，.json 数据归属数据目录 |

---

*最后更新: 2026-06-27*
