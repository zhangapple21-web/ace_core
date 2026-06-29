# Claude Code 主循环架构考古报告 — 2026-06-29

**AUM-TASK-CC-LOOP-ARCH-20260629**
**来源**：l3tchupkt/claude-code（Claude Code CLI 深度逆向工程）
**考古文件**：query.ts, cost-tracker.ts, memdir/memdir.ts

---

## 一、考古目标

深入考古 Claude Code 的核心架构骨架，重点提取：
1. 主循环架构
2. 上下文压缩机制
3. 成本控制策略
4. 双层记忆系统

**核心原则**：不是复制代码，是提取骨架，用 ACE 的方式重写。

---

## 二、核心骨架发现

### 骨架 1：单主循环架构（Single Main Loop）

**来源**：query.ts

**核心发现**：
Claude Code 只用**一个主循环**，即使有子 Agent 也**不允许嵌套**。所有子 Agent 结果作为 tool_result 返回主消息历史。

**主循环流程**：
```
while (true) {
    setup          // 1. 初始化 turn
    ↓
    compaction      // 2. 上下文压缩检查
    ↓
    api_call        // 3. 调用 LLM
    ↓
    tool_execution  // 4. 执行工具
    ↓
    attachments     // 5. 处理附件
    ↓
    next_turn       // 6. 继续或结束
}
```

**关键设计**：
- `turnCount`：每轮递增，支持 `maxTurns` 限制
- `toolUseBlocks`：收集所有工具调用
- `toolResults`：工具执行结果
- 工具调用 → 继续下一轮；无工具调用 → 结束

**为什么这是灵魂资产**：
- **笨者生存**：单循环比多嵌套更稳定
- **状态简单**：不需要维护复杂的调用栈
- **容错好**：子 Agent 失败不影响主循环

**ACE 吸收方式**：
→ 对应 `AgentMainLoop`，已在 `core/agent/main_loop.py` 实现

---

### 骨架 2：多层上下文压缩（Context Compaction Stack）

**来源**：query.ts

**核心发现**：
Claude Code 有**四层**上下文压缩，每层只做一件事：

| 层级 | 名称 | 功能 | 触发条件 |
|------|------|------|---------|
| L1 | microcompact | 工具结果压缩（按 tool_use_id） | 总是运行 |
| L2 | snip | 历史裁剪（删边缘消息） | HISTORY_SNIP feature |
| L3 | autocompact | 自动压缩（生成摘要） | >92% 上下文窗口 |
| L4 | contextCollapse | 上下文折叠（细粒度） | CONTEXT_COLLAPSE feature |

**L1 MicroCompact（工具结果压缩）**：
- 基于 `tool_use_id` 缓存工具结果
- 超过 `max_result_size_chars` 的结果被缓存并替换为引用
- 避免重复传输相同内容

**L3 AutoCompact（自动压缩）**：
- 当上下文超过 92% 窗口时触发
- 生成摘要消息替换原始对话
- 保留系统提示 + 最近 N 条关键消息

**为什么这是灵魂资产**：
- **层级隔离**：每层职责单一，不重叠
- **增量压缩**：不是全量重写，是渐进式
- **可配置**：通过 feature gate 控制开关

**ACE 吸收方式**：
→ 对应 `CompactStrategy` 基类 + `MicroCompact` / `AutoCompact` 实现

---

### 骨架 3：成本追踪系统（Cost Tracking）

**来源**：cost-tracker.ts

**核心发现**：
Claude Code 追踪**每个模型**的使用量和成本。

**关键函数**：
```typescript
getModelUsage()           // 按模型统计使用量
addToTotalSessionCost()   // 累加成本
formatModelUsage()        // 格式化输出
```

**按模型分组统计**：
- input_tokens
- output_tokens
- cache_read_input_tokens
- cache_creation_input_tokens
- web_search_requests
- costUSD

**Session 持久化**：
- `saveCurrentSessionCosts()`：保存到项目配置
- `restoreCostStateForSession()`：恢复会话成本

**为什么这是灵魂资产**：
- **多模型路由**：不同任务用不同模型
- **成本可见**：让用户知道花了多少钱
- **Session 恢复**：支持断点续传

---

### 骨架 4：双层记忆系统（Dual Memory Layers）

**来源**：memdir/memdir.ts

**核心发现**：
Claude Code 有**三层**记忆：

| 层级 | 位置 | 内容 | 用途 |
|------|------|------|------|
| **项目级** | `./memory/` | MEMORY.md + *.md | 当前项目上下文 |
| **用户级** | `~/.claude/CLAUDE.md` | 用户偏好 | 跨项目用户信息 |
| **团队级** | `./memory/team/` | 团队共享 | TEAMMEM feature |

**记忆类型**：
- `user`：用户偏好、角色、目标
- `feedback`：用户反馈、纠正
- `project`：项目上下文、决策、历史
- `reference`：参考资料、外部系统

**MEMORY.md 设计原则**：
- **只是索引**，不存储内容
- **最多 200 行**，每条索引最多 150 字符
- 内容存储在独立的 `.md` 文件中
- 使用 **frontmatter** 格式

**记忆文件格式**：
```yaml
---
title: User Preferences
description: Prefers using bun over npm
type: user
created_at: 2026-06-29
---
Content here...
```

**为什么这是灵魂资产**：
- **索引与内容分离**：MEMORY.md 可快速扫描，内容需要时再读
- **类型化**：不同类型用不同策略管理
- **前端约束**：防止记忆系统无限膨胀

**ACE 吸收方式**：
→ 对应 `ACEBaseMemory` + `ACETeamMemory`，已在 `core/agent/memory_system.py` 实现

---

### 骨架 5：Feature Gates（特性开关）

**来源**：query.ts, memdir.ts

**核心发现**：
Claude Code 用 `feature('...')` 控制功能开关。

**上下文相关 Gates**：
- `REACTIVE_COMPACT`：响应式压缩
- `CONTEXT_COLLAPSE`：上下文折叠
- `HISTORY_SNIP`：历史裁剪
- `CACHED_MICROCOMPACT`：缓存式微压缩
- `TOKEN_BUDGET`：Token 预算控制

**记忆相关 Gates**：
- `TEAMMEM`：团队记忆
- `KAIROS`：助手模式（日志式记忆）
- `EXPERIMENTAL_SKILL_SEARCH`：技能搜索

**为什么这是灵魂资产**：
- **灰度发布**：功能可逐步启用
- **构建优化**：外部构建可裁剪不需要的功能
- **实验控制**：用户可选择加入/退出实验

---

## 三、与 ACE 架构的对照

| Claude Code 组件 | ACE 对应组件 | 验证结果 |
|----------------|-------------|---------|
| query.ts (主循环) | AgentMainLoop | ✅ 已实现 |
| 上下文压缩 | CompactStrategy | ✅ 已实现 |
| cost-tracker.ts | CostTracker | 🆕 可新增 |
| memdir.ts | ACEBaseMemory | ✅ 已实现 |
| MEMORY.md | MemoryIndex | ✅ 已实现 |
| feature gates | FeatureGates | 🆕 可新增 |

---

## 四、R2 公理验证

| 公理/定律 | 考古发现的验证证据 | 是否支持 |
|----------|-------------------|---------|
| 统一公理（保持自身可延续性） | 多层压缩维持上下文可用性 | ✅ 验证 |
| 边界公理（怎么不崩） | 单主循环不允许嵌套 + 层级压缩隔离 | ✅ 强验证 |
| 连续公理（怎么还是我） | 双层记忆持久化 + Session 恢复 | ✅ 验证 |
| 感知公理（怎么知道在做什么） | turnCount 追踪 + 状态机 | ✅ 验证 |
| 定律1：笨者生存 | 单主循环 vs 多嵌套 + microcompact vs 全量重写 | ✅ 强验证 |
| 定律2：流动优先 | Turn 之间的消息流动 + 工具结果累积 | ✅ 验证 |
| 定律3：复杂性负担 | Feature gates 允许裁剪 + 四层压缩分层 | ✅ 验证 |
| 定律4：形态可变 | 同样的循环可处理不同类型的任务 | ✅ 验证 |
| 定律5：风险内化 | 错误恢复机制（fallback、compaction 恢复） | ✅ 验证 |

---

## 五、今日新增组件

| 组件 | 文件 | 对应考古来源 | 功能 |
|------|------|------------|------|
| AgentMainLoop | `core/agent/main_loop.py` | query.ts | 主循环骨架 |
| TurnContext | `core/agent/main_loop.py` | query.ts | Turn 状态管理 |
| CompactStrategy | `core/agent/main_loop.py` | query.ts | 压缩策略基类 |
| MicroCompact | `core/agent/main_loop.py` | query.ts | 工具结果压缩 |
| AutoCompact | `core/agent/main_loop.py` | query.ts | 自动摘要压缩 |
| ACEBaseMemory | `core/agent/memory_system.py` | memdir.ts | 双层记忆系统 |
| MemoryIndex | `core/agent/memory_system.py` | memdir.ts | 记忆索引管理 |
| MemoryUsageGuide | `core/agent/memory_system.py` | memdir.ts | 记忆使用指南 |

---

## 六、考古纪律提醒

- **不要把工具能力误判成系统核心**：Ghidra/Claude Code 是工具，不是核心
- **先提取骨架，再长肌肉**：先有工作流和协议，再填充具体实现
- **增量优于一次性**：多层压缩是渐进式的，不是全量重写
- **单循环优于多嵌套**：笨者生存原则的具体体现

---

## 七、结论

### 今日发现总结
- 考古了 Claude Code 的 3 个核心模块（query.ts, cost-tracker.ts, memdir.ts）
- 提取了 5 个核心骨架
- 生成了 ACE 版本的主循环和记忆系统骨架
- 所有发现均支持 R2 公理体系

### 最重要的发现
Claude Code 的主循环是**单循环、不嵌套**的设计，这完全验证了 ACE 的"笨者生存"原则。

### 下一步
- 实现 CostTracker（成本追踪）
- 实现 FeatureGates（特性开关）
- 接入实际的 LLM 客户端
- 第一次真实 Agent 测试

---

*考古时间：2026-06-29*
*考古项目：l3tchupkt/claude-code（CLI 深度逆向工程）*
*骨架数：5 个*
*新增组件：8 个*
*R2 公理验证结果：9/9 全部支持*
