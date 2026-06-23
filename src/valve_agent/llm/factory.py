"""Provider 工厂:按环境自动选择 DeepSeek / Qwen 或离线 stub。

优先级:
  1. DEEPSEEK_API_KEY → DeepSeek
  2. DASHSCOPE_API_KEY  → Qwen
  3. 否则               → 离线 stub

可用 VALVE_AGENT_LLM 强制指定:
  VALVE_AGENT_LLM=deepseek → DeepSeek
  VALVE_AGENT_LLM=qwen     → Qwen
  VALVE_AGENT_LLM=offline  → 离线 stub
"""

from __future__ import annotations

import os

from .base import LLMProvider
from .offline import OfflineProvider


def _has_deepseek() -> bool:
    return bool(os.environ.get("DEEPSEEK_API_KEY"))


def _has_qwen() -> bool:
    return bool(os.environ.get("DASHSCOPE_API_KEY"))


def get_provider(prefer: str | None = None) -> LLMProvider:
    """返回一个可用的 LLMProvider。

    prefer: "deepseek" | "qwen" | "offline" | None(自动)。
    """
    choice = (prefer or os.environ.get("VALVE_AGENT_LLM", "auto")).lower()

    if choice == "offline":
        return OfflineProvider()

    # -- DeepSeek --
    if choice in ("deepseek", "auto") and _has_deepseek():
        try:
            from .deepseek import DeepSeekProvider

            return DeepSeekProvider()
        except Exception:
            pass  # 降级继续尝试 Qwen

    # -- Qwen --
    if choice in ("qwen", "auto") and _has_qwen():
        try:
            from .qwen import QwenProvider

            return QwenProvider()
        except Exception:
            pass  # 安全回退

    # -- 强制指定但无 key --
    if choice == "deepseek" and not _has_deepseek():
        return OfflineProvider()
    if choice == "qwen" and not _has_qwen():
        return OfflineProvider()

    return OfflineProvider()


def provider_status() -> str:
    """人类可读的当前 LLM 状态,供 CLI 显示。"""
    p = get_provider()
    return p.name


# ---------------------------------------------------------------------------
# 对话式 Agent(chat / function calling)——需要真实大模型
# ---------------------------------------------------------------------------
def chat_available() -> bool:
    """对话式 Agent 是否可用(是否配置了真实大模型)。

    离线 stub 只能做 complete(),无法驱动多步工具调用,故 chat 必须有 key。
    支持 DeepSeek 或 Qwen。
    """
    forced = os.environ.get("VALVE_AGENT_LLM", "").lower()
    if forced == "offline":
        return False
    return _has_deepseek() or _has_qwen()


def get_chat_provider():
    """返回一个支持 chat()/function calling 的 Provider(ChatLLMProvider)。

    优先 DeepSeek,其次 Qwen。无可用真实模型时抛 RuntimeError。
    """
    if not chat_available():
        raise RuntimeError(
            "对话式 Agent 需要真实大模型:请设置 DEEPSEEK_API_KEY 或 DASHSCOPE_API_KEY"
            "(或接入私有模型)。确定性核心与表单页仍可离线使用。"
        )
    if _has_deepseek():
        from .deepseek import DeepSeekProvider

        return DeepSeekProvider()
    if _has_qwen():
        from .qwen import QwenProvider

        return QwenProvider()
    raise RuntimeError("无可用大模型 Provider")
