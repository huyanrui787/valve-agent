"""对话式 Agent 的 API 服务层(对应方案 M2)。

职责:
  - 维护服务端 ChatSession 会话(支持确认门的多次往返)
  - 把 AgentEvent 序列化为 SSE 行
  - 在无真实模型时给出明确降级信息(对应方案 12.7)

会话存储为进程内字典(演示用);生产可换 Redis 等。
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator

from ..agent import ChatSession, build_default_registry
from ..agent.events import AgentEvent
from ..llm import chat_available, get_chat_provider
from .deps import get_kb


# 进程内会话表:session_id -> ChatSession
_SESSIONS: dict[str, ChatSession] = {}


def chat_status() -> dict:
    """对话能力可用性,供前端决定是否展示聊天页 / 降级提示。"""
    return {"available": chat_available()}


def _new_session() -> tuple[str, ChatSession]:
    provider = get_chat_provider()  # 无 key 抛 RuntimeError
    registry = build_default_registry(get_kb())
    session = ChatSession(provider, registry)
    sid = uuid.uuid4().hex
    _SESSIONS[sid] = session
    return sid, session


def _sse(event: str, data: dict) -> str:
    """格式化一条 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _stream_events(sid: str, events: Iterator[AgentEvent]) -> Iterator[str]:
    """把 AgentEvent 流转成 SSE 行,首行带回 session_id。"""
    yield _sse("session", {"session_id": sid})
    for ev in events:
        yield _sse(ev.type, ev.model_dump())
    yield _sse("done", {"session_id": sid})


def start_chat_stream(message: str) -> Iterator[str]:
    """开启一轮对话并流式产出 SSE。无真实模型时产出 error 事件。"""
    try:
        sid, session = _new_session()
    except RuntimeError as e:
        yield _sse("error", {"message": str(e), "downgrade": True})
        yield _sse("done", {})
        return
    yield from _stream_events(sid, session.run(message))


def confirm_chat_stream(session_id: str, call_id: str, approved: bool) -> Iterator[str]:
    """对挂起的写操作确认 / 拒绝,继续流式推进。"""
    session = _SESSIONS.get(session_id)
    if session is None:
        yield _sse("error", {"message": f"会话不存在或已过期:{session_id}"})
        yield _sse("done", {})
        return
    yield from _stream_events(session_id, session.confirm(call_id, approved))
