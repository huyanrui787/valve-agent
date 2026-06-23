"""Agent 运行时(对话式 Agent 2.0)。

把确定性引擎包装成工具(tools),用 ReAct 循环(loop)驱动多步编排,
以事件流(events)产出,写操作经确认门拦截。LLM 只规划与表达,不碰运算。
"""

from __future__ import annotations

from .events import (
    AgentEvent,
    AwaitConfirmEvent,
    ErrorEvent,
    MessageEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from .loop import DEFAULT_SYSTEM, MAX_STEPS, ChatSession
from .tools import Tool, ToolRegistry, build_default_registry

__all__ = [
    "ChatSession",
    "MAX_STEPS",
    "DEFAULT_SYSTEM",
    "Tool",
    "ToolRegistry",
    "build_default_registry",
    "AgentEvent",
    "ThinkingEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "AwaitConfirmEvent",
    "MessageEvent",
    "ErrorEvent",
]
