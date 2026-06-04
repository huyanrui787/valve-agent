"""内存向量库。"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .embeddings import EmbeddingProvider, HashEmbedding


@dataclass
class RagDocument:
    id: str
    text: str
    source: str = ""
    kind: str = ""
    metadata: dict = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)


class VectorStore:
    """简易内存向量检索。"""

    def __init__(self, embedder: EmbeddingProvider | None = None) -> None:
        self.embedder = embedder or HashEmbedding()
        self._docs: list[RagDocument] = []

    def clear(self) -> None:
        self._docs.clear()

    def add(self, doc_id: str, text: str, *, source: str = "", kind: str = "", metadata: dict | None = None) -> None:
        emb = self.embedder.embed([text])[0]
        self._docs.append(
            RagDocument(
                id=doc_id, text=text, source=source, kind=kind,
                metadata=metadata or {}, embedding=emb,
            )
        )

    def search(self, query: str, top_k: int = 5, *, kind: str | None = None) -> list[tuple[RagDocument, float]]:
        if not self._docs:
            return []
        q_emb = self.embedder.embed([query])[0]
        scored: list[tuple[RagDocument, float]] = []
        for d in self._docs:
            if kind and d.kind != kind:
                continue
            scored.append((d, _cosine(q_emb, d.embedding)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @property
    def size(self) -> int:
        return len(self._docs)


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
