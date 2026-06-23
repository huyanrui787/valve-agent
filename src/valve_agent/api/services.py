"""API 业务编排(复用 Agent,不重复引擎逻辑)。"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import UploadFile

from ..agents import BidAgent, QuoteAgent, QuoteRequestLine
from ..agents.bid_agent import BidPackage
from ..documents import load_document
from ..documents.tender_parser import TenderDocumentParser
from ..engines import Quotation
from ..engines.selection import SelectionResult
from ..integrations import FileSyncAdapter
from ..llm import ConditionParser, provider_status
from ..models.tender import ParsedTender
from ..rag import RagRetriever, get_embedder as _get_embedder
from .deps import get_bid_agent, get_project_store, get_quote_agent
from .schemas import (
    BatchRequest,
    BatchResponse,
    BidProjectDetail,
    BidProjectList,
    BidProjectSave,
    BidProjectSummary,
    HealthResponse,
    QuoteRequest,
    RagSearchRequest,
    RagSearchResponse,
    SelectRequest,
    SyncBidRequest,
    SyncQuoteRequest,
    SyncResponse,
    TenderBidResponse,
)


def health() -> HealthResponse:
    return HealthResponse(llm=provider_status())


def select(req: SelectRequest) -> SelectionResult:
    qa = get_quote_agent()
    cond = ConditionParser().parse(req.spec)
    return qa.selector.select(cond, top_n=req.top_n)


def quote_line(req: QuoteRequest) -> LineOutcome:
    return get_quote_agent().quote_text(
        req.spec,
        quantity=req.quantity,
        customer_tier=req.customer_tier,
        is_export=req.is_export,
        price_basis=req.price_basis,
    )


def quote_batch(req: BatchRequest) -> BatchResponse:
    lines = [QuoteRequestLine(text=l.text, quantity=l.quantity) for l in req.lines]
    quotation, outcomes = get_quote_agent().quote_batch(
        lines,
        customer=req.customer,
        customer_tier=req.customer_tier,
        is_export=req.is_export,
        price_basis=req.price_basis,
    )
    return BatchResponse(quotation=quotation, outcomes=outcomes)


def parse_tender_text(text: str, source: str = "") -> ParsedTender:
    return TenderDocumentParser().parse(text, source=source)


async def parse_tender_upload(file: UploadFile) -> ParsedTender:
    suffix = Path(file.filename or "upload.txt").suffix.lower()
    if suffix not in {".pdf", ".docx", ".doc", ".txt", ".md"}:
        raise ValueError(f"不支持的文件类型:{suffix}")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        text = load_document(tmp_path)
        return parse_tender_text(text, source=file.filename or tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def rag_search(req: RagSearchRequest) -> RagSearchResponse:
    ret = RagRetriever(get_quote_agent().kb)
    hits = ret.search(req.query, top_k=req.top_k, kind=req.kind or None)
    return RagSearchResponse(embedder=_get_embedder().name, hits=hits)


def tender_bid_from_parsed(tender: ParsedTender, spec: str, price_basis: date | None) -> TenderBidResponse:
    qa = get_quote_agent()
    ba = get_bid_agent()
    oc = qa.quote_text(spec, quantity=1, price_basis=price_basis)
    if oc.selection is None or oc.selection.best is None:
        return TenderBidResponse(
            tender=tender, selection=oc.selection, quote_error=oc.error or "未选到型号",
        )
    best = oc.selection.best
    pkg = ba.build_from_tender(
        tender, best.product, bid_date=price_basis,
        chosen_body=best.chosen_body_material,
    )
    return TenderBidResponse(tender=tender, selection=oc.selection, package=pkg)


async def tender_bid_upload(
    spec: str,
    file: UploadFile | None,
    price_basis: date | None,
    customer: str,
) -> TenderBidResponse:
    tender: ParsedTender
    if file and file.filename:
        tender = await parse_tender_upload(file)
    else:
        tender = ParsedTender()
    resp = tender_bid_from_parsed(tender, spec, price_basis)
    return resp


def export_quote_docx(req: QuoteRequest) -> tuple[Path, str]:
    oc = quote_line(req)
    if oc.quote is None:
        raise ValueError(oc.error or "报价失败")
    q = Quotation(
        customer=req.customer,
        customer_tier=req.customer_tier,
        is_export=req.is_export,
        price_basis=req.price_basis or date.today(),
        lines=[oc.quote],
    )
    out = Path(tempfile.mkstemp(suffix=".docx")[1])
    get_quote_agent().export_quotation_docx(q, out)
    name = f"quote_{oc.quote.product_code}.docx"
    return out, name


def export_bid_docx(
    spec: str,
    tender: ParsedTender | None,
    price_basis: date | None,
    customer: str,
) -> tuple[Path, str, BidPackage]:
    if tender is None:
        tender = ParsedTender()
    resp = tender_bid_from_parsed(tender, spec, price_basis)
    if resp.package is None:
        raise ValueError(resp.quote_error or "无法生成投标包")
    out = Path(tempfile.mkstemp(suffix=".docx")[1])
    get_bid_agent().export_docx(resp.package, out, tender=tender, customer=customer)
    return out, f"bid_{resp.package.product_code}.docx", resp.package


def sync_quote(req: SyncQuoteRequest) -> SyncResponse:
    oc = quote_line(QuoteRequest(
        spec=req.spec, quantity=1, customer_tier=req.customer_tier, customer=req.customer,
    ))
    if oc.quote is None:
        raise ValueError(oc.error or "报价失败")
    q = Quotation(customer=req.customer, lines=[oc.quote])
    qa = get_quote_agent()
    crm = qa.sync_to_crm(q, sync_dir=req.sync_dir, customer=req.customer)
    erp = qa.sync_to_erp(q, sync_dir=req.sync_dir, project_code=req.project_code)
    return SyncResponse(crm=crm, erp_cost=erp)


def _demo_requirements():
    from ..models import CompareOp, TenderRequirement

    return [
        TenderRequirement(param="公称压力", op=CompareOp.GE, target_value=40,
                          unit="bar", is_critical=True),
        TenderRequirement(param="工作温度", op=CompareOp.GE, target_value=300,
                          unit="℃", is_critical=True),
        TenderRequirement(param="执行标准", op=CompareOp.IN, target_set=["API"],
                          is_critical=True),
    ]


def sync_bid(req: SyncBidRequest) -> SyncResponse:
    qa = get_quote_agent()
    ba = get_bid_agent()
    oc = qa.quote_text(req.spec)
    if not oc.selection or not oc.selection.best:
        raise ValueError("未选到型号")
    pkg = ba.build_package(
        oc.selection.best.product, _demo_requirements(),
        chosen_body=oc.selection.best.chosen_body_material,
    )
    adapter = FileSyncAdapter(req.sync_dir)
    erp_bid = adapter.push_bid_snapshot(pkg, project_code=req.project_code)
    return SyncResponse(erp_bid=erp_bid)


# ---------------------------------------------------------------------------
# 标书项目记录(内容生成后留存,可重新打开续编)
# ---------------------------------------------------------------------------
def _to_summary(p) -> BidProjectSummary:
    return BidProjectSummary(
        id=p.id, project_name=p.project_name, status=p.status,
        word_count=p.word_count, created_at=p.created_at, updated_at=p.updated_at,
    )


def _to_detail(p) -> BidProjectDetail:
    return BidProjectDetail(
        id=p.id, project_name=p.project_name, status=p.status,
        word_count=p.word_count, created_at=p.created_at, updated_at=p.updated_at,
        spec=p.spec, snapshot=p.snapshot,
    )


def create_project(req: BidProjectSave) -> BidProjectDetail:
    p = get_project_store().create(
        project_name=req.project_name, word_count=req.word_count,
        spec=req.spec, status=req.status, snapshot=req.snapshot,
    )
    return _to_detail(p)


def list_projects() -> BidProjectList:
    items = [_to_summary(p) for p in get_project_store().list()]
    return BidProjectList(items=items, total=len(items))


def get_project(project_id: str) -> BidProjectDetail:
    p = get_project_store().get(project_id)
    if p is None:
        raise KeyError(project_id)
    return _to_detail(p)


def update_project(project_id: str, req: BidProjectSave) -> BidProjectDetail:
    p = get_project_store().update(
        project_id, project_name=req.project_name, word_count=req.word_count,
        spec=req.spec, status=req.status, snapshot=req.snapshot,
    )
    if p is None:
        raise KeyError(project_id)
    return _to_detail(p)
