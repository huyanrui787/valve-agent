"""招标文件解析、导出、RAG、集成测试。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from valve_agent.agents import BidAgent, QuoteAgent
from valve_agent.documents import TenderDocumentParser, load_document
from valve_agent.documents.export import export_bid_docx, export_quotation_docx
from valve_agent.integrations import FileSyncAdapter
from valve_agent.models import CompareOp, TenderRequirement
from valve_agent.rag import HashEmbedding, KnowledgeIndexer, RagRetriever, VectorStore


SAMPLE_TENDER = Path(__file__).resolve().parents[1] / "examples" / "sample_tender.txt"


def test_load_sample_tender_text():
    text = load_document(SAMPLE_TENDER)
    assert "公称压力" in text
    assert "废标" in text


def test_tender_parser_extracts_requirements():
    text = load_document(SAMPLE_TENDER)
    parsed = TenderDocumentParser().parse(text, source=str(SAMPLE_TENDER))
    assert parsed.brief.bid_deadline == date(2026, 7, 15)
    assert "ISO9001" in parsed.brief.required_qual_categories
    assert parsed.brief.min_track_records >= 3
    assert parsed.brief.industry_hint == "电力"
    params = {r.param for r in parsed.requirements}
    assert "公称压力" in params
    assert "工作温度" in params
    assert len(parsed.waste_clauses) >= 1


def test_rag_search_products(kb):
    store = VectorStore(embedder=HashEmbedding())
    KnowledgeIndexer(store).index_kb(kb)
    hits = store.search("球阀 DN200 蒸汽", top_k=3, kind="product")
    assert hits
    assert any("Q41" in d.text or "球阀" in d.text for d, _ in hits)


def test_rag_retriever(kb):
    ret = RagRetriever(kb)
    hits = ret.search("API 认证 电力业绩", top_k=5)
    assert len(hits) >= 1


def test_bid_from_tender_file(kb, basis, tmp_path):
    ba = BidAgent(kb)
    tender = ba.parse_tender_file(SAMPLE_TENDER)
    from valve_agent.agents import QuoteAgent

    oc = QuoteAgent(kb).quote_text("球阀 DN200 PN40 蒸汽 250℃ 电动 API 316", price_basis=basis)
    pkg = ba.build_from_tender(tender, oc.selection.best.product,
                               bid_date=basis,
                               chosen_body=oc.selection.best.chosen_body_material)
    assert pkg.deviation_table.items
    out = tmp_path / "bid.docx"
    export_bid_docx(pkg, out, tender=tender)
    assert out.stat().st_size > 2000


def test_export_quotation_docx(kb, basis, tmp_path):
    oc = QuoteAgent(kb).quote_text("蝶阀 DN300 PN16 水 80℃ 电动", price_basis=basis)
    from valve_agent.engines import Quotation

    q = Quotation(lines=[oc.quote])
    path = export_quotation_docx(q, tmp_path / "quote.docx")
    assert path.exists()


def test_file_sync_crm_erp(kb, basis, tmp_path):
    oc = QuoteAgent(kb).quote_text("球阀 DN200 PN40 蒸汽 250℃ 电动 316", price_basis=basis)
    from valve_agent.engines import Quotation

    q = Quotation(customer="测试客户", lines=[oc.quote])
    adapter = FileSyncAdapter(tmp_path / "sync")
    crm = adapter.push_quotation(q, customer="测试客户")
    erp = adapter.push_quotation_cost(q, project_code="PRJ-001")
    assert crm.ok and (tmp_path / "sync" / "crm" / "quotations").exists()
    assert erp.ok
    ba = BidAgent(kb)
    pkg = ba.build_package(
        oc.selection.best.product,
        [TenderRequirement(param="公称压力", op=CompareOp.GE, target_value=40, unit="bar")],
        bid_date=basis,
    )
    bid_res = adapter.push_bid_snapshot(pkg, project_code="PRJ-001")
    assert bid_res.ok
