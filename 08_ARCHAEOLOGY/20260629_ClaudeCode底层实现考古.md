# Claude-Code 底层实现结构考古 — 2026-06-29 补

**AUM-TASK-CC-REVERSE-20260629**
**来源**：知乎专栏 - 作者从 0 实现 Claude-Code 类似工具
**链接**：https://zhuanlan.zhihu.com/p/2020197591703368604

---

## 一、考古目标

通过逆向工程提取 Claude-Code 的底层架构骨架，验证 ACE 已有设计，寻找可以吸收的灵魂资产。

**核心发现**：Claude-Code 没有用 RAG 或复杂框架，就是日常工具的组合。这和 ACE 的"极简工具 + 治理层"哲学完全一致。

---

## 二、核心骨架发现

### 骨架 1：极简工具哲学（Unix 哲学的 AI 版本）

Claude-Code 的 22 个工具，没有一个是"大而全"的：

| 需求 | ❌ 不要用 | ✅ 应该用 |
|------|---------|---------|
| 搜索文件 | find, ls (Bash) | Glob |
| 搜索内容 | grep, rg (Bash) | Grep |
| 读取文件 | cat, head, tail (Bash) | Read |
| 编辑文件 | sed, awk (Bash) | Edit |
| 写入文件 | echo >, cat <<EOF (Bash) | Write |
| 输出文本 | echo, printf (Bash) | 直接输出文本 |

**为什么这是灵魂资产**：
- **专用工具 > 通用工具**：每件事有最适合的工具，AI 不需要自己推理该用什么
- **约束即自由**：明确的"不要做什么"反而让 AI 更高效
- **对抗上下文腐烂**：小工具 = 低上下文消耗

**对 ACE 的验证**：ACE 的 FileBus 工具集（Read, Edit, Write, Glob, Grep）完全对标 Claude-Code，无需改动。

---

### 骨架 2：子代理类型系统（Agent Subagent Types）

Claude-Code 的 Agent 工具有 5 种专用类型：

| 代理类型 | 说明 | 可用工具 |
|---------|------|---------|
| **general-purpose** | 通用代理，研究复杂问题 | 全部工具 (*) |
| **statusline-setup** | 配置用户状态行 | Read, Edit |
| **Explore** | 快速探索代码库 | 除 Agent, ExitPlanMode, Edit, Write, NotebookEdit |
| **Plan** | 软件架构师代理 | 除 Agent, ExitPlanMode, Edit, Write, NotebookEdit |
| **claude-code-guide** | 回答 Claude Code CLI 问题 | Glob, Grep, Read, WebFetch, WebSearch |

**参数设计亮点**：
```json
{
  "description": "A short (3-5 word) description of the task",
  "prompt": "The task for the agent to perform",
  "subagent_type": "specialized agent type",
  "model": "Optional model override (sonnet/opus/haiku)",
  "run_in_background": "true = background task",
  "isolation": "'worktree' creates a temporary git worktree"
}
```

**为什么这是灵魂资产**：
- **隔离设计**：worktree 隔离避免污染主仓库
- **模型路由**：不同任务用不同模型（haiku 便宜快，opus 贵但准）
- **背景执行**：不阻塞主流程

**对 ACE 的启发**：ACE 已有 `general_purpose_task` 和 `search` 两种 subagent_type，可以补充：
- `explore` - 快速探索（深度可配置）
- `plan` - 架构师模式（只读，不写）
- `execute` - 执行模式（有写权限）

---

### 骨架 3：用户意图预测系统（Next Action Prediction）

任务完成后，Claude-Code 会预测用户下一步行为：

**判断标准**：
> 用户看到后会不会觉得：**"对，我刚刚正准备输入这个。"**

**示例逻辑**：
- bug 修好了 → 预测"运行测试"
- 代码写完了 → 预测"试一下"
- 提供了选项 → 预测用户最可能选的那个
- 出现错误 → **保持沉默**（不要替用户做决定）

**格式要求**：
- 2-12 个词
- 匹配用户说话风格
- 或者**什么都不输出**

**为什么这是灵魂资产**：
- **主动预测 > 被动等待**：不等人问，主动给建议
- **约束边界**：明确列出"绝对不要建议"的内容
- **沉默也是选项**：不确定时选择不打扰

**对 ACE 的启发**：ACE 可以实现类似的"下一步预测"机制：
- 任务完成后调用 `predict_next_action()`
- 输出给用户选择
- 或者静默等待

---

### 骨架 4：技能系统（Skills）

Claude-Code 的 4 个内置技能：

| 技能名称 | 触发场景 | 对应 ACE 概念 |
|---------|---------|-------------|
| **update-config** | 配置 settings.json（hooks、权限、环境变量） | Constraint（约束管理） |
| **simplify** | 代码 review，让代码更简洁 | Validator（质量验证） |
| **loop** | 循环执行/定时重复任务 | Schedule（定时任务） |
| **claude-api** | Claude API / Anthropic SDK 开发 | Router（技能路由） |

**为什么这是灵魂资产**：
- **技能是可扩展的**：不是硬编码，是可注册的模块
- **场景触发**：不是主动调用，是"当遇到 X 场景时激活"
- **轻量级**：不需要启动完整 Agent，开销小

**对 ACE 的验证**：ACE 的 Skill 系统（`skill_creator`, `gh-cli`, `pdf` 等）完全对标，可以继续扩展。

---

### 骨架 5：System Prompt 的约束哲学

Claude-Code 的 System Prompt 核心原则：

**执行任务的原则**：
- 不要在没读过代码的情况下就乱提修改建议
- 除非必要，不要新建文件
- 不要过度设计
- 只做用户明确要求或明显必要的事
- 不要顺手加功能、重构、注释、兼容层、特性开关等多余内容

**风险操作原则**：
- **先确认范围，再动手**
- **不要用破坏性手段偷懒**

**为什么这是灵魂资产**：
- **约束即自由**：明确的边界让 AI 不会越界
- **最小化干预**：不帮人做决定，只帮人执行
- **风险前置**：高风险操作必须确认，不默许

**对 ACE 的验证**：ACE 的 Constraint 层（"风险内化"、"先查配置再改"）完全对标。

---

### 骨架 6：自动记忆机制（Persistent Memory）

Claude-Code 的 memory 目录使用原则：

**应该写入 memory 的**：
- 稳定模式
- 用户偏好
- 架构信息
- 已验证经验

**不应该写入 memory 的**：
- 临时状态
- 未验证信息
- 当前会话的一次性细节

**为什么这是灵魂资产**：
- **区分记忆层级**：工作记忆 vs 长期记忆
- **验证后才沉淀**：未验证的不写入，避免污染
- **增量积累**：每次会话都让系统更懂用户

**对 ACE 的验证**：ACE 的 Memory Index（"结构沉淀为骨架"）完全对标，理念一致。

---

### 骨架 7：Harness Engineering 理念

作者在文章最后总结：

> **底层（模型）做的更强大，应用层应用要做更薄。对应到 Harness Engineering，就是所有的实现交给模型+工具，工程师只要设计目标，约束和验证方案即可。**

这和 ACE 的核心理念完全一致：

| 维度 | Harness Engineering | ACE |
|------|---------------------|-----|
| 底层 | 更强大的模型 | ACE 的 Router/Lexicon 层 |
| 应用层 | 做更薄 | ACE 的文件总线（轻量执行） |
| 工程师角色 | 设计目标、约束、验证方案 | ACE 的治理层（Constraint/Validator） |
| 实现交给 | 模型 + 工具 | Worker + Tool |

---

## 三、与 ACE 的完整对照

| Claude-Code 组件 | ACE 对应组件 | 验证结果 |
|----------------|-------------|---------|
| 工具系统（Glob/Grep/Read/Edit/Write） | FileBus 工具集 | ✅ 完全对标 |
| 子代理类型（Explore/Plan/General） | Task subagent_type | ✅ 已实现，需补充 |
| 技能系统（Skills） | ACE Skill 系统 | ✅ 完全对标 |
| 约束原则（System Prompt） | Constraint 层 | ✅ 完全对标 |
| 自动记忆（Memory） | Memory Index | ✅ 完全对标 |
| 用户意图预测 | （缺失） | 🆕 可新增 |
| 风险操作确认 | Validator 层 | ✅ 部分对标 |
| 定时任务（Loop） | Schedule 工具 | ✅ 完全对标 |

---

## 四、可吸收的新骨架

### 骨架 A：用户意图预测器（Next Action Predictor）

```python
class NextActionPredictor:
    """用户意图预测器 — 任务完成后预测用户下一步"""
    
    def predict(self, task_result: Dict[str, Any]) -> Optional[str]:
        """
        返回 2-12 词的预测，或 None（保持沉默）
        """
        # 规则：
        # - bug 修好了 → "运行测试"
        # - 代码写完了 → "试一下"
        # - 出现错误 → None（不打扰）
        # - 不确定 → None
        pass
```

### 骨架 B：代理隔离机制（Worktree Isolation）

```python
class IsolatedAgent:
    """隔离代理 — 在临时 git worktree 中执行"""
    
    def execute(self, task: str, worktree_name: str) -> str:
        """
        1. 创建临时 worktree
        2. 在 worktree 中执行任务
        3. 合并结果（或丢弃）
        4. 清理 worktree
        """
        pass
```

### 骨架 C：模型路由（Model Routing）

```python
MODEL_ROUTING = {
    "quick": "haiku",      # 快速探索、简单任务
    "medium": "sonnet",    # 标准分析
    "deep": "opus",        # 深度推理、复杂问题
}
```

---

## 五、考古纪律验证

| 纪律 | 验证结果 |
|------|---------|
| 不要把工具能力误判成系统核心 | ✅ Claude-Code 的核心是"约束+极简"，不是工具本身 |
| 先提取骨架，再长肌肉 | ✅ 没有 RAG，就是工具组合 |
| 增量优于一次性 | ✅ memory 增量积累，skill 可扩展 |
| 证据优先于结论 | ✅ System Prompt 有明确的"不要建议"列表 |

---

## 六、结论

**最重要发现**：Claude-Code 的底层实现**完全验证**了 ACE 的核心哲学。

- 没有 RAG → ACE 不需要 RAG
- 极简工具 → ACE 的 FileBus
- 约束即自由 → ACE 的 Constraint 层
- 自动记忆 → ACE 的 Memory Index
- 模型做强大，应用做薄 → ACE 的 Router 层

**唯一缺失**：用户意图预测系统。这是 ACE 可以吸收的新骨架。

**下一步**：
1. 实现 NextActionPredictor
2. 补充 subagent_type（explore, plan）
3. 实现 WorktreeIsolation

---

*考古时间：2026-06-29*
*来源：知乎专栏逆向工程 Claude-Code*
*骨架数：7 个核心 + 3 个可吸收新骨架*
