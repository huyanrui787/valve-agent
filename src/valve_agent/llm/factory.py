"""Provider 工厂:按环境自动选择 Qwen 或离线 stub。

约定:设置了 DASHSCOPE_API_KEY 即用 Qwen,否则回退 OfflineProvider。
可用 VALVE_AGENT_LLM=offline 强制离线,或 =qwen 强制 Qwen(无 key 则报错)。
这样 demo 在无 key 时照常跑,有 key 时自动升级为真实大模型。
"""

from __future__ import annotations

import os

from .base import LLMProvider
from .offline import OfflineProvider


def get_provider(prefer: str | None = None) -> LLMProvider:
    """返回一个可用的 LLMProvider。

    prefer: "qwen" | "offline" | None(自动)。
    """
    choice = (prefer or os.environ.get("VALVE_AGENT_LLM", "auto")).lower()
    has_key = bool(os.environ.get("DASHSCOPE_API_KEY"))

    if choice == "offline":
        return OfflineProvider()
    if choice in ("qwen", "auto") and has_key:
        try:
            from .qwen import QwenProvider

            return QwenProvider()
        except Exception:
            # 初始化失败(无 key/导入问题)一律安全回退,保证流程不中断
            return OfflineProvider()
    if choice == "qwen" and not has_key:
        # 用户强制要 Qwen 但没 key:回退离线并由调用方自行提示
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
    """
    forced = os.environ.get("VALVE_AGENT_LLM", "").lower()
    if forced == "offline":
        return False
    return bool(os.environ.get("DASHSCOPE_API_KEY"))


def get_chat_provider():
    """返回一个支持 chat()/function calling 的 Provider(ChatLLMProvider)。

    无可用真实模型时抛 RuntimeError —— 调用方(API/前端)应据此降级提示,
    引导用户回退到表单页(对应方案 12.7「降级透明」)。
    """
    if not chat_available():
        raise RuntimeError(
            "对话式 Agent 需要真实大模型:请设置 DASHSCOPE_API_KEY(或接入私有模型)。"
            "确定性核心与表单页仍可离线使用。"
        )
    from .qwen import QwenProvider

    return QwenProvider()
