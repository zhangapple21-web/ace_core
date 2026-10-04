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
2. **hunk 级暂存只在"索引结构 == 工作区结构"时安全。**
   `git apply --cached --unidiff-zero` 按索引行号落位。一旦对方的结构改动只存在于
   工作区，锚点就会指进容器中间，提交物变成**嵌合体**：工作区全绿，提交版本编译
   不过。2026-10-04 我因此连续两次把 `ace_daemon.py` 的方法插进字典字面量、把
   `core/task_roles.py` 的过滤条件插进 `_model_objections`；两次 CI 都没抓住，因为
   那版 `verify_fixes.py` 根本不 import `ace_daemon`。
   **对策**：共享文件正在被别人结构重构时，不要 hunk 级暂存 —— 要么等对方收工，
   要么重建整个文件（基线 + 我的块，锚点逐个断言存在于基线里）。
3. **验证提交物，不是工作区。** 提交后至少跑一次
   `git show HEAD:<file> | python -c "import sys;compile(sys.stdin.read(),'f','exec')"`；
   更省事的是让 `ops/verify_fixes.py` 第 2c 项编译核心模块（已加），CI 会替你盯。
4. **改了 `ace_daemon.py` 就跑 `python ops/verify_fixes.py`。** 其中 2b 项是复用的接线
   护栏，2c 项是编译护栏。接线被抹掉时 CI 会红，不该等到某个交付静默失败才发现。
5. **各自的改动各自提交。** 共享文件里不要 `git add .`；用精确标记挑自己的 hunk。
6. **移动已提交代码时，两半一起动。** 挪位置会让 diff 一边 `-` 一边 `+`；只提交其中
   一半会复制或删掉已入库的代码。
7. **发现自己覆盖了对方的行，立刻说，别默默继续。**

## CI 护栏自身也要能跨机器跑

`ops/verify_fixes.py` 在 GitHub 的裸 Python 上跑。凡是 `import ace_daemon` 这类会
拖进第三方依赖（`requests`）的检查，都必须降级为"文本断言优先、import 只是补充证据"，
否则一次环境差异就会把流水线刷红，而红的理由和代码质量无关。

## 已落库的位置

- 复用读取器：`core/knowledge_reuse.py`（唯一 owner），daemon 阶段
  `_run_knowledge_reuse_stage`，默认 `enabled=false` + `dry-run`。
- 接线护栏：`ops/verify_fixes.py` 第 2b 项（文本断言，不 import）。
- 端到端护栏：`ops/test_knowledge_reuse_daemon_stage.py::test_verified_delivery_records_the_reuse_contribution`
  —— 交付阶段一旦不记录复用贡献就红。