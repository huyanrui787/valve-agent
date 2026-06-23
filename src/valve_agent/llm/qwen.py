"""Qwen(阿里云 DashScope)LLM Provider。

走 DashScope 的 OpenAI 兼容端点,只用标准库 urllib 调用,不引入重 SDK。
读取环境变量 DASHSCOPE_API_KEY(或显式传入 api_key)。

体现方案"模型可替换":本类实现与 OfflineProvider 相同的 complete() 接口,
两个 Agent 无需感知具体模型。无 key / 网络不通时由 get_provider() 回退到离线。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .base import ChatMessage, ChatResult, ToolCall

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"
EMBED_MODEL = "text-embedding-v3"


class QwenError(RuntimeError):
    """Qwen 调用失败。"""


class QwenProvider:
    """阿里云 Qwen 大模型 Provider(DashScope OpenAI 兼容模式)。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        embed_model: str = EMBED_MODEL,
    ) -> None:
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        if not self.api_key:
            raise QwenError("缺少 DASHSCOPE_API_KEY,无法初始化 QwenProvider")
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.embed_model = embed_model

    @property
    def name(self) -> str:
        return f"qwen:{self.model}"

    # ------------------------------------------------------------------
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        """对话补全。返回模型文本。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }
        data = self._post("/chat/completions", body)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            raise QwenError(f"Qwen 返回结构异常:{data}") from e

    # ------------------------------------------------------------------
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[dict] | None = None,
        system: str = "",
    ) -> ChatResult:
        """多轮对话 + 工具调用(function calling),驱动 Agent ReAct 循环。

        走 DashScope OpenAI 兼容端点的 tools / tool_calls 字段。
        """
        wire = self._to_wire_messages(messages, system)
        body: dict = {
            "model": self.model,
            "messages": wire,
            "temperature": 0.2,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        data = self._post("/chat/completions", body)
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError) as e:
            raise QwenError(f"Qwen 返回结构异常:{data}") from e

        raw_calls = msg.get("tool_calls") or []
        calls: list[ToolCall] = []
        for tc in raw_calls:
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "") or "{}"
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(
                id=tc.get("id") or f"call_{len(calls)}",
                name=fn.get("name", ""),
                arguments=args if isinstance(args, dict) else {},
            ))
        return ChatResult(content=(msg.get("content") or "").strip(), tool_calls=calls)

    @staticmethod
    def _to_wire_messages(messages: list[ChatMessage], system: str) -> list[dict]:
        """ChatMessage → DashScope/OpenAI 线格式。"""
        wire: list[dict] = []
        if system:
            wire.append({"role": "system", "content": system})
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                wire.append({
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {"id": c.id, "type": "function",
                         "function": {"name": c.name,
                                      "arguments": json.dumps(c.arguments, ensure_ascii=False)}}
                        for c in m.tool_calls
                    ],
                })
            elif m.role == "tool":
                wire.append({"role": "tool", "tool_call_id": m.tool_call_id,
                             "content": m.content})
            else:
                wire.append({"role": m.role, "content": m.content})
        return wire

    def embed(self, texts: list[str]) -> list[list[float]]:
        """文本向量化,供 RAG 使用。"""
        body = {"model": self.embed_model, "input": texts}
        data = self._post("/embeddings", body)
        try:
            items = sorted(data["data"], key=lambda d: d["index"])
            return [it["embedding"] for it in items]
        except (KeyError, IndexError) as e:
            raise QwenError(f"Qwen embedding 返回结构异常:{data}") from e

    # ------------------------------------------------------------------
    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:500]
            raise QwenError(f"Qwen HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise QwenError(f"Qwen 网络错误:{e.reason}") from e
