"""RAG 检索编排。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..knowledge import KnowledgeBase
from ..models.tender import ParsedTender
from .indexer import KnowledgeIndexer
from .store import RagDocument, VectorStore


class RagHit(BaseModel):
    id: str
    text: str
    source: str
    kind: str
    score: float
    metadata: dict = Field(default_factory=dict)


class RagRetriever:
    """对企业知识库与招标文本做语义检索。"""

    def __init__(self, kb: KnowledgeBase, store: VectorStore | None = None) -> None:
        self.kb = kb
        self.indexer = KnowledgeIndexer(store=store)
        self.store = self.indexer.store
        self._indexed = False

    def ensure_indexed(self, tender: ParsedTender | None = None) -> None:
        if not self._indexed:
            self.indexer.index_kb(self.kb)
            self._indexed = True
        if tender and tender.raw_text:
            self.indexer.index_tender(tender)

    def search(self, query: str, top_k: int = 5, *, kind: str | None = None) -> list[RagHit]:
        self.ensure_indexed()
        hits = self.store.search(query, top_k=top_k, kind=kind)
        return [
            RagHit(
                id=d.id, text=d.text, source=d.source, kind=d.kind,
                score=round(score, 4), metadata=d.metadata,
            )
            for d, score in hits
        ]

    def context_for_proposal(self, product_code: str, query: str, tender: ParsedTender | None = None) -> str:
        """为技术方案撰写组装检索上下文。"""
        self.ensure_indexed(tender)
        parts: list[str] = []
        for hit in self.search(f"{product_code} {query}", top_k=3, kind="product"):
            parts.append(f"[产品库] {hit.text}")
        for hit in self.search(query, top_k=2, kind="tender"):
            parts.append(f"[招标文件] {hit.text[:300]}")
        for hit in self.search(query, top_k=2, kind="track_record"):
            parts.append(f"[业绩] {hit.text}")
        return "\n".join(parts) if parts else ""
