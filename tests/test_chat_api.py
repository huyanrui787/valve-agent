"""M2 测试:Qwen function calling 线格式 + /api/chat SSE 端点。

不调真实 DashScope:
  - Qwen 部分只测纯函数 _to_wire_messages(消息 → 线格式),不发网络;
  - SSE 端点通过 monkeypatch 注入 MockChatProvider,验证流式事件与确认门往返。
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from valve_agent.api.app import create_app
from valve_agent.llm import ChatMessage, ChatResult, MockChatProvider, ToolCall
from valve_agent.llm.qwen import QwenProvider


# ---------------------------------------------------------------------------
# Qwen 线格式转换(纯函数,无网络)
# ---------------------------------------------------------------------------
def test_qwen_wire_messages_roundtrip():
    msgs = [
        ChatMessage(role="user", content="报个价"),
        ChatMessage(role="assistant", content="好的",
                    tool_calls=[ToolCall(id="c1", name="quote",
                                         arguments={"spec": "球阀 DN200 PN40"})]),
        ChatMessage(role="tool", tool_call_id="c1", name="quote",
                    content='{"unit_price": 100}'),
    ]
    wire = QwenProvider._to_wire_messages(msgs, system="你是助手")
    assert wire[0] == {"role": "system", "content": "你是助手"}
    # assistant 带 tool_calls,arguments 序列化为字符串
    asst = wire[2]
    assert asst["role"] == "assistant"
    assert asst["tool_calls"][0]["function"]["name"] == "quote"
    assert json.loads(asst["tool_calls"][0]["function"]["arguments"])["spec"].startswith("球阀")
    # tool 消息带 tool_call_id
    assert wire[3]["role"] == "tool" and wire[3]["tool_call_id"] == "c1"


# ---------------------------------------------------------------------------
# SSE 端点:用 MockChatProvider 注入
# ---------------------------------------------------------------------------
def _parse_sse(text: str) -> list[tuple[str, dict]]:
    """解析 SSE 文本为 [(event, data_dict)]。"""
    out = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if ev:
            out.append((ev, data))
    return out


@pytest.fixture
def client():
    return TestClient(create_app())


def test_chat_status_offline(client, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("VALVE_AGENT_LLM", "offline")
    r = client.get("/api/chat/status")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_chat_offline_downgrade(client, monkeypatch):
    """无 key 时 /api/chat 应产出 downgrade error,而非崩溃。"""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("VALVE_AGENT_LLM", "offline")
    r = client.post("/api/chat", json={"message": "报价"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert "error" in kinds
    err = next(d for e, d in events if e == "error")
    assert err.get("downgrade") is True


def test_chat_stream_with_mock(client, monkeypatch):
    """注入 MockChatProvider:单步报价 → 收尾,验证 SSE 事件序列。"""
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="quote",
                   arguments={"spec": spec, "quantity": 10, "customer_tier": "A"})]),
        ChatResult(content="已完成报价。"),
    ])
    monkeypatch.setattr("valve_agent.api.chat_service.chat_available", lambda: True)
    monkeypatch.setattr("valve_agent.api.chat_service.get_chat_provider", lambda: mock)

    r = client.post("/api/chat", json={"message": "给某电厂报个价"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "session"
    assert "tool_call" in kinds and "tool_result" in kinds
    assert "message" in kinds and kinds[-1] == "done"
    # 工具结果数值来自引擎
    tr = next(d for e, d in events if e == "tool_result")
    assert tr["result"]["product_code"] == "Q41F-40P"


def test_chat_confirm_roundtrip(client, monkeypatch):
    """写操作:首轮命中 await_confirm,confirm 端点放行后执行并收尾。"""
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 316"
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="w1", name="export_quote_docx",
                                        arguments={"spec": spec, "quantity": 2})]),
        ChatResult(content="已导出报价单。"),
    ])
    monkeypatch.setattr("valve_agent.api.chat_service.chat_available", lambda: True)
    monkeypatch.setattr("valve_agent.api.chat_service.get_chat_provider", lambda: mock)

    r = client.post("/api/chat", json={"message": "导出报价单"})
    events = _parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert "await_confirm" in kinds
    session_id = next(d for e, d in events if e == "session")["session_id"]
    call_id = next(d for e, d in events if e == "await_confirm")["call_id"]
    # 此时还没执行写工具
    assert "tool_result" not in kinds

    r2 = client.post("/api/chat/confirm", json={
        "session_id": session_id, "call_id": call_id, "approved": True})
    events2 = _parse_sse(r2.text)
    kinds2 = [e for e, _ in events2]
    assert "tool_result" in kinds2 and "message" in kinds2
    tr = next(d for e, d in events2 if e == "tool_result")
    assert tr["ok"] is True and tr["result"]["path"].endswith(".docx")
