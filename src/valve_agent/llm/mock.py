"""Mock 对话 Provider —— 供单测/CI 验证 Agent 运行时,不调真实 API。

按脚本返回预设的 ChatResult 序列(每次 chat() 取下一个),
从而确定性地驱动 ReAct 循环、确认门与工具编排逻辑(对应方案 12.8)。

用法:
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="quote",
                                        arguments={"spec": "..."})]),
        ChatResult(content="已为你完成报价:..."),
    ])
每调用一次 chat() 消费一个脚本项;脚本耗尽后返回最后一项的兜底文本。
"""

from __future__ import annotations

from .base import ChatMessage, ChatResult


class MockChatProvider:
    """脚本化对话 Provider。"""

    name = "mock-chat"

    def __init__(self, script: list[ChatResult], *, name: str = "mock-chat") -> None:
        if not script:
            raise ValueError("MockChatProvider 需要至少一个脚本项")
        self.name = name
        self._script = list(script)
        self._i = 0
        self.calls: list[dict] = []  # 记录每次 chat 的入参,供断言

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        system: str = "",
    ) -> ChatResult:
        self.calls.append({
            "messages": list(messages),
            "tool_count": len(tools or []),
            "system": system,
        })
        if self._i < len(self._script):
            res = self._script[self._i]
            self._i += 1
            return res
        # 脚本耗尽:返回一个收尾文本,避免循环卡死
        return ChatResult(content="(mock)脚本已结束")
