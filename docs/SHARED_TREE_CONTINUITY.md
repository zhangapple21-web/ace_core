# 共享树连续性协议（两个写者同时改同一个 checkout）

这不是架构文档，是一份操作约定。写它是因为代价已经付过一次。

## 发生过什么

2026-10-04，另一个窗口和我同时在 `C:\tmp\ace_core` 这一个 checkout 上工作。
`ace_daemon.py` 的归档知识复用接线被整段抹掉两次：

- 00:58:46 —— `_reuse_hint_for`（交付 worker prompt 携带旧知识的那一段）消失；
- 随后 —— 交付贡献核算接线与 `__init__` 里的计数器属性一起消失。第二次有真实
  故障面：交付阶段会抛 `AttributeError` 并记 `status: ERROR`，`delivered` 静默
  归零。

## 为什么：不是信息没共享，是 lost update

1. 对方**知道**这套功能：他们的未提交文本里写着"归档知识复用的唯一 owner 是
   `core/knowledge_reuse.py::KnowledgeReuseGate`（daemon 阶段
   `_run_knowledge_reuse_stage`，默认 `dry-run`）"。信息是通的，被抹的是代码。
2. 被抹的位置永远是**双方都在写的那一段**：`ace_daemon.py` 的
   lifecycle/delivery 区。我们的 hunk 相邻 13 处。
3. 决定性证据：文件 mtime **倒流** —— 我 01:02 写完，mtime 变成 23:38:54，
   且只存在于 00:45 之后的内容整块消失。定点 edit 做不到这件事，只有拿旧快照
   **整文件覆盖**做得到。git stash 空、无新提交、无 `.orig` 备份。

## 约定

1. **不要拿旧快照整文件覆盖共享文件。** 要回退某段，就只回退那段（定点 edit），
   不要 `git checkout` / `Copy-Item` 整个文件覆盖别人的新行。
2. **改了 `ace_daemon.py` 就跑 `python ops/verify_fixes.py`。** 其中 2b 项是这套
   复用的接线护栏：接线被抹掉时 CI 会红，不该等到某个交付静默失败才发现。
3. **各自的改动各自提交，hunk 级归属。** 共享文件里不要 `git add .`；用精确标记
   挑自己的 hunk 暂存（本次用过 `git apply --cached --unidiff-zero`）。
4. **移动已提交代码时，两半一起动。** 如果只是挪位置，diff 会一边 `-` 一边 `+`；
   只提交其中一半会复制或删掉已入库的代码。
5. **发现自己覆盖了对方的行，立刻说，别默默继续。**

## 已落库的位置

- 复用读取器：`core/knowledge_reuse.py`（唯一 owner），daemon 阶段
  `_run_knowledge_reuse_stage`，默认 `enabled=false` + `dry-run`。
- 接线护栏：`ops/verify_fixes.py` 第 2b 项（文本断言，不 import）。
- 端到端护栏：`ops/test_knowledge_reuse_daemon_stage.py::test_verified_delivery_records_the_reuse_contribution`
  —— 交付阶段一旦不记录复用贡献就红。