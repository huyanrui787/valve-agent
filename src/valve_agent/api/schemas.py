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
