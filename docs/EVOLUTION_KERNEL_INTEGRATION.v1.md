# ACE Evolution Kernel：研究成果到现实能力的唯一闭环

这次吸收的不是另一套人格或另一条后台进程，而是一个收敛层。它把本地视频王国、ACE 核心、Trae 试验结果、失败复盘和外部研究放进同一个中间语义包，避免“写了很多规则却没人消费”。

## 继承什么

- **分层记忆**：工作记忆、会话/项目记忆、长期知识和失败经验分开；文件与收据是跨窗口事实，聊天上下文不是永久记忆。
- **语义中间层**：每个候选都拆成 `facts / evidence / inferences / unknowns / experience`，不再把模型猜测混入事实。
- **词库/模板优先**：稳定的生产规则先复用，模型只补齐缺口；新模板必须经过真实结果验证。
- **统一路由**：内部失败和本地指标优先于外部灵感；外部矿只能进入 Research/TaskPool，不能静默改生产。
- **痛苦复盘**：记录代价、未拦截时的反事实后果、复发风险和可复用教训。
- **单一治理声音**：观察者、路由器、工程师、评审、守门人等是功能席位，不是相互冲突的人格；Guardian 的否决仍然有效。

## 不继承什么

- 不把“连续意识”“跨窗口记忆”当作平台能力，必须落到仓库、哈希、收据和可重放输入。
- 不因为一次模型回答、一次漂亮样片或一次通过就晋升能力。
- 不执行外部仓库代码、不安装外部依赖、不上传本地素材和密钥。
- 不新增第二个任务池、第二个调度器或第二条视频入口。

## 真实闭环

```text
观察（聊天/文件/收据/指标）
  → 语义归一化（事实/证据/推断/未知）
  → 路由（先修本地失败，再研究外部）
  → 既有 TaskPool / DailyLearning 做实验
  → baseline / change / test / evaluation
  → painful_review
  → PROMOTE 或 ROLLBACK_REQUIRED
  → LearningReturnBridge 生成受限能力卡
  → 视频王国只消费 RESEARCH_READY_NOT_PROMOTED，复测后再进生产门
```

`core/evolution_kernel.py` 只负责归一化、路由、门禁和桥接收据；它不取得执行权。`VideoLearningBridgeBacklog` 只把已规范化的 `RESEARCH` 包适配成既有候选，实际生命周期仍由 `DailyLearningLoop` → `TaskPool` → `Researcher/Validator/Guardian` → `LearningReturnBridge` 完成；没有第二个闭环。

## 视频王国的反哺边界

视频王国外部学习收据通过 `tools/publish_ace_learning_packet.py` 单向写入 ACE 的 `08_GOVERNANCE/video_learning_bridge/`。每个收据默认是 `RESEARCH`，必须在 ACE 里完成本地 A/B、真实失败复盘和无回归比较，才有资格进入能力卡；能力卡仍禁止自动改 Provider、默认模型、视频入口或真实媒体任务。

## 系统指标

夜间任务不以“改了多少代码”为指标，而观察：重复失败率、候选到验证的比例、误晋升数、回滚数、任务墙最老年龄、单次验证成本、从失败到修复的时间。没有新证据或指标改善时保持安静。
