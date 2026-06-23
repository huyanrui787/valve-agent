"""REST API 请求/响应模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..agents.bid_agent import BidPackage
from ..agents.quote_agent import LineOutcome
from ..engines import Quotation
from ..engines.selection import SelectionResult
from ..integrations import SyncResult
from ..models.tender import ParsedTender
from ..rag.retriever import RagHit


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    llm: str = ""


class SelectRequest(BaseModel):
    spec: str
    top_n: int = Field(3, ge=1, le=10)
    show_rejections: bool = False


class QuoteRequest(BaseModel):
    spec: str
    quantity: int = Field(1, ge=1)
    customer_tier: str = "C"
    is_export: bool = False
    price_basis: date | None = None
    customer: str = ""


class BatchLineIn(BaseModel):
    text: str
    quantity: int = Field(1, ge=1)


class BatchRequest(BaseModel):
    lines: list[BatchLineIn]
    customer: str = ""
    customer_tier: str = "C"
    is_export: bool = False
    price_basis: date | None = None


class BatchResponse(BaseModel):
    quotation: Quotation
    outcomes: list[LineOutcome]


class RagSearchRequest(BaseModel):
    query: str
    top_k: int = Field(5, ge=1, le=20)
    kind: str | None = None


class RagSearchResponse(BaseModel):
    embedder: str
    hits: list[RagHit]


class TenderBidRequest(BaseModel):
    spec: str
    customer: str = ""
    price_basis: date | None = None


class TenderBidResponse(BaseModel):
    tender: ParsedTender
    selection: SelectionResult | None = None
    quote_error: str | None = None
    package: BidPackage | None = None


class SyncQuoteRequest(BaseModel):
    spec: str
    customer: str = ""
    customer_tier: str = "C"
    project_code: str = ""
    sync_dir: str = "./sync"


class SyncBidRequest(BaseModel):
    spec: str
    project_code: str = ""
    sync_dir: str = "./sync"


class SyncResponse(BaseModel):
    crm: SyncResult | None = None
    erp_cost: SyncResult | None = None
    erp_bid: SyncResult | None = None


class BidProjectSave(BaseModel):
    """创建/更新标书项目记录的入参。snapshot 为前端续编所需的整份状态。"""

    project_name: str = "未命名标书"
    word_count: int = 0
    spec: str = ""
    status: str = "completed"
    snapshot: dict = Field(default_factory=dict)


class BidProjectSummary(BaseModel):
    """列表项:只含展示与排序所需的元数据,不含 snapshot。"""

    id: str
    project_name: str
    status: str
    word_count: int
    created_at: str
    updated_at: str


class BidProjectDetail(BidProjectSummary):
    """详情:在元数据基础上带回 spec 与续编所需的 snapshot。"""

    spec: str = ""
    snapshot: dict = Field(default_factory=dict)


class BidProjectList(BaseModel):
    items: list[BidProjectSummary]
    total: int


class ChatStatusResponse(BaseModel):
    available: bool


class ChatRequest(BaseModel):
    message: str


class ChatConfirmRequest(BaseModel):
    session_id: str
    call_id: str
    approved: bool
