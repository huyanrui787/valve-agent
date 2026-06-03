"""LLM Provider 抽象接口(体现方案"模型可替换""规则保准确、模型保表达")。

底座设计为模型可替换:任何实现 LLMProvider 协议的类都可注入两个 Agent。
默认提供 OfflineProvider(规则化离线实现),保证 demo 无需密钥/算力即可运行;
生产环境可替换为国产大模型(私有化/内网)的实现。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    """大模型提供方协议。

    只负责"表达"类任务(理解意图、撰写文字、润色话术),
    不负责选型/报价/偏离判定这些"准确"类硬逻辑。
    """

    name: str

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        """给定提示词返回文本补全。"""
        ...
