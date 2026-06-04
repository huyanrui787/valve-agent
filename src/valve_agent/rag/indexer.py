"""知识底座与招标文件索引。"""

from __future__ import annotations

from ..knowledge import KnowledgeBase
from ..models.tender import ParsedTender
from .chunk import chunk_text
from .embeddings import EmbeddingProvider, get_embedder
from .store import VectorStore


class KnowledgeIndexer:
    """将六库与招标文本写入向量库。"""

    def __init__(self, store: VectorStore | None = None, embedder: EmbeddingProvider | None = None) -> None:
        self.store = store or VectorStore(embedder=embedder or get_embedder())

    def index_kb(self, kb: KnowledgeBase) -> int:
        """索引产品/资质/业绩,返回新增条数。"""
        self.store.clear()
        n = 0
        for code, p in kb.products.items():
            text = (
                f"{p.code} {p.name} {p.valve_type.value} "
                f"DN{p.dn_range.min_dn}-{p.dn_range.max_dn} "
                f"PN{p.pn_range.min_pn:g}-{p.pn_range.max_pn:g} "
                f"温度{p.temp_range.min_c:g}-{p.temp_range.max_c:g}℃ "
                f"阀体{'/'.join(p.body_materials)} 标准{'/'.join(s.value for s in p.standards)}"
            )
            self.store.add(f"product:{code}", text, source="product", kind="product",
                           metadata={"code": code})
            n += 1
        for q in kb.qualifications:
            text = f"{q.category} {q.name} 编号{q.cert_no} 有效期至{q.valid_until}"
            self.store.add(f"qual:{q.cert_no}", text, source="qualification", kind="qualification",
                           metadata={"category": q.category})
            n += 1
        for r in kb.track_records:
            text = (
                f"业绩 {r.project_name} 客户{r.customer} 行业{r.industry} "
                f"{r.valve_type} {r.contract_date} 合同额{r.amount}"
            )
            self.store.add(f"record:{r.project_name[:40]}:{r.contract_date}", text,
                           source="track_record", kind="track_record",
                           metadata={"industry": r.industry})
            n += 1
        return n

    def index_tender(self, tender: ParsedTender) -> int:
        """把招标原文分块入库(不清空已有索引)。"""
        chunks = chunk_text(tender.raw_text)
        n = 0
        for i, ch in enumerate(chunks):
            self.store.add(f"tender:{tender.source}:{i}", ch, source=tender.source or "tender",
                           kind="tender", metadata={"chunk": i})
            n += 1
        return n
