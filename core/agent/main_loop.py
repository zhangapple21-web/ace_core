"""
ACE Agent Main Loop

主循环状态机，负责协调：
1. Setup - turn 初始化
2. API Call - 调用 LLM
3. Tool Execution - 执行工具
4. Attachments - 处理大结果
5. Next Turn - 继续下一轮

参考：Claude Code query.ts 的核心骨架
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Any, Optional, Generator


class TurnState(Enum):
    SETUP = "setup"
    API_CALL = "api_call"
    TOOL_EXECUTION = "tool_execution"
    ATTACHMENTS = "attachments"
    NEXT_TURN = "next_turn"
    DONE = "done"


@dataclass
class StreamEvent:
    """流式输出事件"""
    type: str
    data: Any


@dataclass
class TurnContext:
    """单个 turn 的上下文状态"""
    turn_count: int = 1
    max_turns: int = 10
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_use_blocks: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    state: TurnState = TurnState.SETUP
    should_continue: bool = True
    compacted: bool = False


@dataclass
class QueryParams:
    """主循环输入参数"""
    messages: List[Dict[str, Any]]
    max_turns: int = 10
    model: str = "claude-3-opus"
    temperature: float = 0.7


@dataclass
class CompactionResult:
    """压缩结果"""
    pre_compact_token_count: int
    post_compact_token_count: int
    summary_messages: List[Dict[str, Any]]
    attachments: List[Dict[str, Any]]


class CompactStrategy:
    """压缩策略接口"""

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        raise NotImplementedError

    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        raise NotImplementedError


class MicroCompact(CompactStrategy):
    """
    工具结果压缩

    基于 call_id 或 tool_use_id 缓存工具结果，避免重复传输。
    对重复调用同一工具的场景特别有效（如 Read 同一个文件多次）。
    """

    def __init__(self, max_result_size: int = 10000):
        self.max_result_size = max_result_size
        self._cache: Dict[str, str] = {}

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        return True

    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        compacted = []
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                new_content = []
                for block in msg["content"]:
                    if block.get("type") in {"tool_result", "function_call_output"}:
                        content = block.get("content", block.get("output", ""))
                        tool_id = block.get("call_id") or block.get("tool_use_id", "")
                        if len(str(content)) > self.max_result_size:
                            cache_key = f"cached_{tool_id}"
                            self._cache[cache_key] = str(content)
                            new_block = {
                                "type": "cached_result",
                                "cache_key": cache_key,
                            }
                            if block.get("call_id"):
                                new_block["call_id"] = block["call_id"]
                            if block.get("tool_use_id"):
                                new_block["tool_use_id"] = block["tool_use_id"]
                            new_content.append(new_block)
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
    自动摘要压缩

    当消息过多时，保留最近 N 条 + 历史摘要。
    """

    def __init__(self, threshold: float = 0.92):
        self.threshold = threshold

    def should_compact(self, messages: List[Dict[str, Any]]) -> bool:
        return len(str(messages)) > 50000

    def compact(self, messages: List[Dict[str, Any]]) -> CompactionResult:
        system_messages = [m for m in messages if m.get("role") == "system"]
        recent_messages = messages[-10:]
        summary = self._generate_summary(messages)
        return CompactionResult(
            pre_compact_token_count=self._estimate_tokens(messages),
            post_compact_token_count=self._estimate_tokens(system_messages + recent_messages),
            summary_messages=[{"role": "system", "content": f"[对话摘要] {summary}"}],
            attachments=[],
        )

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return len(str(messages)) // 4

    def _generate_summary(self, messages: List[Dict[str, Any]]) -> str:
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
    """

    def __init__(self, model_client, tool_registry, compaction_strategies: List[CompactStrategy] = None):
        self.model_client = model_client
        self.tool_registry = tool_registry
        self.compaction_strategies = compaction_strategies or [
            MicroCompact(),
            AutoCompact(),
        ]

    def run(self, params: QueryParams) -> Generator[StreamEvent, None, TurnState]:
        state = TurnContext(turn_count=1, messages=params.messages)

        while True:
            yield from self._setup(state)
            state = yield from self._apply_compaction(state, params)
            state = yield from self._api_call(state, params)

            if state.tool_use_blocks:
                state = yield from self._tool_execution(state)
                state = yield from self._process_attachments(state)
                state = yield from self._next_turn(state)
            else:
                state.state = TurnState.DONE
                return state

    def _setup(self, state: TurnContext) -> Generator[StreamEvent, None, TurnContext]:
        state.state = TurnState.SETUP
        yield StreamEvent(type="status", data=f"Turn {state.turn_count}/{state.max_turns}")
        return state

    def _apply_compaction(self, state: TurnContext, params: QueryParams) -> Generator[StreamEvent, None, TurnContext]:
        for strategy in self.compaction_strategies:
            if strategy.should_compact(state.messages):
                yield StreamEvent(type="compacting", data=strategy.__class__.__name__)
                result = strategy.compact(state.messages)
                state.messages = result.summary_messages + state.messages[-10:]
                state.compacted = True
                break
        return state

    def _api_call(self, state: TurnContext, params: QueryParams) -> Generator[StreamEvent, None, TurnContext]:
        state.state = TurnState.API_CALL
        response = self.model_client.stream_chat(
            messages=state.messages,
            model=params.model,
            temperature=params.temperature,
        )
        state.tool_use_blocks = []
        for event in response:
            if event.type == "content_block":
                yield StreamEvent(type="content", data=event.data)
            elif event.type == "tool_use":
                state.tool_use_blocks.append(event.data)
        return state

    def _tool_execution(self, state: TurnContext) -> Generator[StreamEvent, None, TurnContext]:
        state.state = TurnState.TOOL_EXECUTION
        for tool_block in state.tool_use_blocks:
            tool_name = tool_block.get("name")
            tool_input = tool_block.get("input", {})
            tool_id = tool_block.get("id")
            # Responses requires the provider-issued call_id.  Never infer it
            # from the item id: those identifiers are distinct, and guessing
            # would turn a missing-field error into a malformed continuation.
            call_id = tool_block.get("call_id")
            tool = self.tool_registry.get(tool_name)
            if not tool:
                state.tool_results.append(self._build_tool_result(
                    tool_id=tool_id,
                    call_id=call_id,
                    content=f"Tool not found: {tool_name}",
                    is_error=True,
                ))
                continue
            try:
                result = tool.execute(tool_input)
                state.tool_results.append(self._build_tool_result(
                    tool_id=tool_id,
                    call_id=call_id,
                    content=result,
                ))
            except Exception as e:
                state.tool_results.append(self._build_tool_result(
                    tool_id=tool_id,
                    call_id=call_id,
                    content=f"Tool execution failed: {str(e)}",
                    is_error=True,
                ))
        return state

    def _build_tool_result(
        self,
        tool_id: Optional[str],
        call_id: Optional[str],
        content: Any,
        is_error: bool = False,
    ) -> Dict[str, Any]:
        if call_id:
            result = {
                "type": "function_call_output",
                "call_id": call_id,
                "output": content,
            }
            if is_error:
                result["is_error"] = True
            return result

        result = {
            "type": "tool_result",
            "tool_use_id": tool_id,
            "content": content,
        }
        if is_error:
            result["is_error"] = True
        return result

    def _process_attachments(self, state: TurnContext) -> Generator[StreamEvent, None, TurnContext]:
        state.state = TurnState.ATTACHMENTS
        for result in state.tool_results:
            state.messages.append({
                "role": "user",
                "content": [result],
            })
        return state

    def _next_turn(self, state: TurnContext) -> Generator[StreamEvent, None, TurnContext]:
        state.state = TurnState.NEXT_TURN
        state.turn_count += 1
        if state.turn_count > state.max_turns:
            state.state = TurnState.DONE
            state.should_continue = False
            return state
        return state
