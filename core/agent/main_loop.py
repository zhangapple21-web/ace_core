"""
Agent Main Loop — ACE 主循环骨架

从 Claude Code query.ts 考古提取的核心骨架。

核心设计：
- 单主循环，不允许嵌套（笨者生存）
- 每个 turn 包含：setup → api_call → tool_execution → attachments → next_turn
- 多层上下文压缩：microcompact → snip → autocompact → contextCollapse
- 成本控制：TOKEN_BUDGET / taskBudget

这不是复制 Claude Code。
是用 ACE 的方式重写这套骨架。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Generator
from abc import ABC, abstractmethod


class TurnState(Enum):
    """Turn 状态"""
    SETUP = "setup"
    API_CALL = "api_call"
    TOOL_EXECUTION = "tool_execution"
    ATTACHMENTS = "attachments"
    NEXT_TURN = "next_turn"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class TurnContext:
    """Turn 上下文"""
    turn_count: int = 1
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_use_blocks: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    state: TurnState = TurnState.SETUP
    transition_reason: Optional[str] = None


@dataclass
class CompactionResult:
    """压缩结果"""
    pre_compact_token_count: int
    post_compact_token_count: int
    summary_messages: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class QueryParams:
    """查询参数"""
    messages: List[Dict[str, Any]]
    system_prompt: str
    user_context: Dict[str, str] = field(default_factory=dict)
    system_context: Dict[str, str] = field(default_factory=dict)
    max_turns: Optional[int] = None
    task_budget: Optional[int] = None  # 整个 agent turn 的 token 预算


@dataclass
class StreamEvent:
    """流式事件"""
    type: str
    data: Any = None


class CompactStrategy(ABC):
    """
    上下文压缩策略基类

    Claude Code 有多层压缩，ACE 也需要：
    1. microcompact - 工具结果压缩（按 tool_use_id）
    2. snip - 历史裁剪
    3. autocompact - 自动压缩（超过阈值）
    4. contextCollapse - 上下文折叠（更细粒度）

    设计原则：
    - 每层只做一件事
    - 层级之间不重叠
    - 压缩是增量式的，不是全量重写
    """

    @abstractmethod
    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        """判断是否需要压缩"""
        pass

    @abstractmethod
    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        """执行压缩"""
        pass


class MicroCompact(CompactStrategy):
    """
    工具结果压缩

    基于 tool_use_id 缓存工具结果，避免重复传输。
    对重复调用同一工具的场景特别有效（如 Read 同一个文件多次）。
    """

    def __init__(self, max_result_size: int = 10000):
        self.max_result_size = max_result_size
        self._cache: Dict[str, str] = {}

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        # microcompact 总是运行，不需要阈值判断
        return True

    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        """将工具结果替换为缓存引用"""
        compacted = []
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                new_content = []
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        content = block.get("content", "")
                        tool_id = block.get("tool_use_id", "")

                        # 如果结果超过限制，缓存并替换
                        if len(str(content)) > self.max_result_size:
                            cache_key = f"cached_{tool_id}"
                            self._cache[cache_key] = str(content)
                            new_content.append({
                                "type": "cached_result",
                                "cache_key": cache_key,
                                "tool_use_id": tool_id,
                            })
                        else:
                            new_content.append(block)
                    else:
                        new_content.append(block)
                msg = {**msg, "content": new_content}
            compacted.append(msg)

        return CompactionResult(
            pre_compact_token_count=len(str(messages)),
            post_compact_token_count=len(str(compacted)),
            summary_messages=[],
            attachments=[],
        )


class AutoCompact(CompactStrategy):
    """
    自动压缩

    当上下文超过阈值时，自动压缩为摘要。
    Claude Code 的阈值是 92% 上下文窗口。
    """

    def __init__(self, threshold: float = 0.92):
        self.threshold = threshold
        self.context_window = 200000  # 默认上下文窗口
        self.consecutive_failures = 0

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        # 估算 token 数量
        estimated_tokens = self._estimate_tokens(messages)
        return estimated_tokens > self.context_window * self.threshold

    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        """
        生成摘要并替换原始消息

        保留：
        - System prompt
        - 最近 N 条关键消息
        - 压缩后的工具结果

        替换为：
        - 摘要消息（描述被压缩的对话）
        """
        # 提取关键信息
        system_messages = [m for m in messages if m.get("role") == "system"]
        recent_messages = messages[-10:]  # 保留最近 10 条

        # 生成摘要
        summary = self._generate_summary(messages)

        return CompactionResult(
            pre_compact_token_count=self._estimate_tokens(messages),
            post_compact_token_count=self._estimate_tokens(system_messages + recent_messages),
            summary_messages=[{"role": "system", "content": f"[对话摘要] {summary}"}],
            attachments=[],
        )

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """简单估算 token 数量"""
        return len(str(messages)) // 4

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
        """生成摘要"""
        # 从 messages 中提取关键信息
        tool_uses = [
            m for m in messages
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), list)
            and any(b.get("type") == "tool_use" for b in m.get("content", []))
        ]
        return f"压缩了 {len(messages)} 条消息，{len(tool_uses)} 次工具调用"


class AgentMainLoop:
    """
    ACE Agent 主循环

    从 Claude Code query.ts 考古提取的骨架。

    核心流程：
    1. setup - 初始化 turn
    2. api_call - 调用 LLM
    3. tool_execution - 执行工具
    4. attachments - 处理附件
    5. next_turn - 继续下一轮或结束

    设计原则：
    - 单主循环，不允许嵌套子 Agent
    - 子 Agent 结果作为 tool_result 返回主循环
    - 每次 turn 都有 maxTurns 限制
    - 支持多层级上下文压缩
    """

    def __init__(self, model_client, tool_registry, compaction_strategies: List[CompactStrategy] = None):
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.compaction_strategies = compaction_strategies or [
            MicroCompact(),
            AutoCompact(),
        ]

    def run(self, params: QueryParams) -> Generator[StreamEvent, None, TurnState]:
        """
        运行主循环

        这是一个生成器，不是普通函数。
        每个 yield 都是一个流式输出事件。

        返回：
        - StreamEvent：流式事件（token、工具调用等）
        - TurnState：最终状态
        """
        state = TurnContext(turn_count=1, messages=params.messages)

        while True:
            # 1. Setup
            yield from self._setup(state)

            # 2. 上下文压缩检查
            state = yield from self._apply_compaction(state, params)

            # 3. API 调用
            state = yield from self._api_call(state, params)

            # 4. 工具执行
            state = yield from self._tool_execution(state)

            # 5. 附件处理
            state = yield from self._process_attachments(state)

            # 6. 检查是否继续
            if state.tool_use_blocks:
                # 有工具调用，继续下一轮
                state.turn_count += 1
                state.state = TurnState.NEXT_TURN
                state.transition_reason = "next_turn"

                # 检查 maxTurns
                if params.max_turns and state.turn_count > params.max_turns:
                    state.state = TurnState.BLOCKED
                    yield StreamEvent(type="max_turns_reached", data={"max_turns": params.max_turns})
                    return state.state

                continue
            else:
                # 没有工具调用，结束
                state.state = TurnState.COMPLETED
                return state.state

    def _setup(self, state: TurnContext) -> Generator[StreamEvent, None, TurnContext]:
        """Setup 阶段：初始化 turn"""
        state.state = TurnState.SETUP
        state.tool_use_blocks = []
        state.tool_results = []
        yield StreamEvent(type="turn_start", data={"turn": state.turn_count})
        return state

    def _apply_compaction(
        self, state: TurnContext, params: QueryParams
    ) -> Generator[StreamEvent, None, TurnContext]:
        """应用上下文压缩"""
        for strategy in self.compaction_strategies:
            if strategy.should_compact(state.messages):
                result = strategy.compact(state.messages)
                yield StreamEvent(
                    type="compaction",
                    data={
                        "strategy": strategy.__class__.__name__,
                        "before": result.pre_compact_token_count,
                        "after": result.post_compact_token_count,
                    },
                )
                # 更新 messages
                state.messages = result.summary_messages + state.messages[-10:]
        return state

    def _api_call(
        self, state: TurnContext, params: QueryParams
    ) -> Generator[StreamEvent, None, TurnContext]:
        """API 调用阶段"""
        state.state = TurnState.API_CALL

        # 构建请求
        request = {
            "messages": params.system_prompt + state.messages,
            "system": params.system_prompt,
            "user_context": params.user_context,
            "system_context": params.system_context,
        }

        # 调用模型
        response = yield from self.model_client.stream(request)

        # 解析响应
        for event in response:
            if event.type == "content_block":
                yield StreamEvent(type="content", data=event.data)
            elif event.type == "tool_use":
                state.tool_use_blocks.append(event.data)

        return state

    def _tool_execution(
        self, state: TurnContext
    ) -> Generator[StreamEvent, None, TurnContext]:
        """工具执行阶段"""
        state.state = TurnState.TOOL_EXECUTION

        for tool_block in state.tool_use_blocks:
            tool_name = tool_block.get("name")
            tool_input = tool_block.get("input", {})
            tool_id = tool_block.get("id")

            # 查找工具
            tool = self.tool_registry.get(tool_name)
            if not tool:
                state.tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"Tool not found: {tool_name}",
                    "is_error": True,
                })
                continue

            # 执行工具
            try:
                result = tool.execute(tool_input)
                state.tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": result,
                })
            except Exception as e:
                state.tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": f"Tool execution failed: {str(e)}",
                    "is_error": True,
                })

        return state

    def _process_attachments(
        self, state: TurnContext
    ) -> Generator[StreamEvent, None, TurnContext]:
        """附件处理阶段"""
        state.state = TurnState.ATTACHMENTS

        # 将 tool_results 添加到 messages
        for result in state.tool_results:
            state.messages.append({
                "role": "user",
                "content": [result],
            })

        return state
