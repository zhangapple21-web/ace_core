"""
Agent Core — ACE Agent 核心模块

从 Claude Code 逆向工程提取的核心骨架。
"""

from .main_loop import (
    TurnState,
    TurnContext,
    CompactionResult,
    QueryParams,
    StreamEvent,
    CompactStrategy,
    MicroCompact,
    AutoCompact,
    AgentMainLoop,
)

from .memory_system import (
    MemoryType,
    MemoryEntry,
    MemoryIndex,
    MemoryLayer,
    MemoryConfig,
    ACEBaseMemory,
    ACETeamMemory,
    MemoryUsageGuide,
)

__all__ = [
    # Main Loop
    "TurnState",
    "TurnContext",
    "CompactionResult",
    "QueryParams",
    "StreamEvent",
    "CompactStrategy",
    "MicroCompact",
    "AutoCompact",
    "AgentMainLoop",
    # Memory System
    "MemoryType",
    "MemoryEntry",
    "MemoryIndex",
    "MemoryLayer",
    "MemoryConfig",
    "ACEBaseMemory",
    "ACETeamMemory",
    "MemoryUsageGuide",
]
