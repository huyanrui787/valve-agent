"""Agent 运行时事件类型。

ReAct 循环每推进一步就 yield 一个事件,既驱动前端流式渲染,
也是可审计的留痕(调了什么工具、入参、结果)。

事件种类:
  thinking       —— 模型一轮的中间文本(可选,模型边想边说)
  tool_call      —— 模型决定调用某工具(含入参)
  tool_result    —— 工具执行完成的结构化结果
  await_confirm  —— 命中写操作确认门,等待用户确认
  message        —— 最终自然语言答复
  error          —— 某一步出错(工具异常/超步数等)
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "thinking",
    "tool_call",
    "tool_result",
    "await_confirm",
    "message",
    "error",
]


class AgentEvent(BaseModel):
    """运行时事件基类。"""

    type: EventType
    step: int = 0


class ThinkingEvent(AgentEvent):
    type: EventType = "thinking"
    text: str = ""


class ToolCallEvent(AgentEvent):
    type: EventType = "tool_call"
    call_id: str
    tool: str
    arguments: dict = Field(default_factory=dict)
    is_write: bool = False


class ToolResultEvent(AgentEvent):
    type: EventType = "tool_result"
    call_id: str
    tool: str
    ok: bool = True
    result: Any = None
    error: str = ""


class AwaitConfirmEvent(AgentEvent):
    """写操作确认门:列出待确认的写工具调用,等用户放行。"""

    type: EventType = "await_confirm"
    call_id: str
    tool: str
    arguments: dict = Field(default_factory=dict)
    prompt: str = ""


class MessageEvent(AgentEvent):
    type: EventType = "message"
    text: str = ""


class ErrorEvent(AgentEvent):
    type: EventType = "error"
    message: str = ""
