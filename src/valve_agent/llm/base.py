"""LLM Provider 抽象接口(体现方案"模型可替换""规则保准确、模型保表达")。

底座设计为模型可替换:任何实现 LLMProvider 协议的类都可注入两个 Agent。
默认提供 OfflineProvider(规则化离线实现),保证 demo 无需密钥/算力即可运行;
生产环境可替换为国产大模型(私有化/内网)的实现。

对话式 Agent 2.0 在 complete() 之外新增 chat()(function calling):
  - complete() —— 单轮"表达"任务(撰写/润色),离线 stub 即可胜任
  - chat()     —— 多轮 + 工具调用,驱动 ReAct 规划循环,需真实大模型
两条接口分别用两个 Protocol 表达:OfflineProvider 只实现 complete();
能驱动 Agent 的 Provider(Qwen / Mock)实现 ChatLLMProvider。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


@runtime_checkable
class LLMProvider(Protocol):
    """大模型提供方协议(表达类任务)。

    只负责"表达"类任务(理解意图、撰写文字、润色话术),
    不负责选型/报价/偏离判定这些"准确"类硬逻辑。
    """

    name: str

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        """给定提示词返回文本补全。"""
        ...


# ---------------------------------------------------------------------------
# 对话 + 工具调用(function calling)数据模型
# ---------------------------------------------------------------------------
class ToolCall(BaseModel):
    """模型发起的一次工具调用。arguments 为已解析的 JSON 对象。"""

    id: str
    name: str
    arguments: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    """对话历史中的一条消息(贴合 OpenAI/DashScope 线格式)。

    role: system | user | assistant | tool
      - assistant 携带 tool_calls 时表示模型要求调用工具
      - role=tool 用 tool_call_id + name 回喂某次调用的结果
    """

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str = ""
    name: str = ""


class ChatResult(BaseModel):
    """一次 chat() 的返回:要么是文本答复,要么是若干工具调用。"""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @property
    def is_tool_calls(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class ChatLLMProvider(Protocol):
    """支持多轮对话 + 工具调用的大模型协议(驱动 Agent 运行时)。

    tools 为 OpenAI 风格的工具声明列表:
      [{"type": "function", "function": {"name", "description", "parameters"}}]
    """

    name: str

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        system: str = "",
    ) -> ChatResult:
        """给定对话历史与可用工具,返回文本答复或工具调用。"""
        ...
