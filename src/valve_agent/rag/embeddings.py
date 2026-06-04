"""文本向量化(离线哈希 / Qwen API)。"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedding:
    """确定性哈希向量(无网络、无密钥,供测试与离线 RAG)。"""

    name = "hash-embedding"

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        tokens = text.lower().split()
        for tok in tokens:
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        for i in range(len(text) - 1):
            bg = text[i : i + 2].lower()
            h = int(hashlib.md5(bg.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 0.5
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def get_embedder(prefer: str | None = None) -> EmbeddingProvider:
    """有 DASHSCOPE_API_KEY 时用 Qwen embedding,否则哈希向量。"""
    choice = (prefer or os.environ.get("VALVE_AGENT_EMBED", "auto")).lower()
    has_key = bool(os.environ.get("DASHSCOPE_API_KEY"))
    if choice == "hash":
        return HashEmbedding()
    if choice in ("qwen", "auto") and has_key:
        try:
            from ..llm.qwen import QwenProvider

            q = QwenProvider()

            class _QwenEmbed:
                name = f"qwen-embed:{q.embed_model}"

                def embed(self, texts: list[str]) -> list[list[float]]:
                    return q.embed(texts)

            return _QwenEmbed()
        except Exception:
            return HashEmbedding()
    return HashEmbedding()
