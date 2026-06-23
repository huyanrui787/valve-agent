"""REST 路由。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from . import chat_service, services
from .schemas import (
    BatchRequest,
    BatchResponse,
    BidProjectDetail,
    BidProjectList,
    BidProjectSave,
    ChatConfirmRequest,
    ChatRequest,
    ChatStatusResponse,
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
from ..agents.quote_agent import LineOutcome as LineOutcomeModel
from ..engines.selection import SelectionResult
from ..models.tender import ParsedTender

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    return services.health()


@router.post("/quote/select", response_model=SelectionResult)
def api_select(req: SelectRequest) -> SelectionResult:
    try:
        return services.select(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/quote/line", response_model=LineOutcomeModel)
def api_quote(req: QuoteRequest) -> LineOutcomeModel:
    return services.quote_line(req)


@router.post("/quote/batch", response_model=BatchResponse)
def api_batch(req: BatchRequest) -> BatchResponse:
    return services.quote_batch(req)


@router.post("/tender/parse", response_model=ParsedTender)
async def api_parse_tender(file: UploadFile = File(...)) -> ParsedTender:
    try:
        return await services.parse_tender_upload(file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/tender/bid", response_model=TenderBidResponse)
async def api_tender_bid(
    spec: str = Form(...),
    customer: str = Form(""),
    price_basis: str = Form(""),
    file: UploadFile | None = File(None),
) -> TenderBidResponse:
    pb = date.fromisoformat(price_basis) if price_basis else None
    try:
        return await services.tender_bid_upload(spec, file, pb, customer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/rag/search", response_model=RagSearchResponse)
def api_rag(req: RagSearchRequest) -> RagSearchResponse:
    return services.rag_search(req)


@router.post("/export/quote")
def api_export_quote(req: QuoteRequest):
    try:
        path, filename = services.export_quote_docx(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return FileResponse(path, filename=filename, media_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ))


@router.post("/export/bid")
async def api_export_bid(
    spec: str = Form(...),
    customer: str = Form(""),
    price_basis: str = Form(""),
    file: UploadFile | None = File(None),
):
    pb = date.fromisoformat(price_basis) if price_basis else None
    tender = await services.parse_tender_upload(file) if file and file.filename else None
    try:
        path, filename, _ = services.export_bid_docx(spec, tender, pb, customer)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return FileResponse(path, filename=filename, media_type=(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ))


@router.post("/sync/quote", response_model=SyncResponse)
def api_sync_quote(req: SyncQuoteRequest) -> SyncResponse:
    try:
        return services.sync_quote(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/sync/bid", response_model=SyncResponse)
def api_sync_bid(req: SyncBidRequest) -> SyncResponse:
    try:
        return services.sync_bid(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ---------------------------------------------------------------------------
# 标书项目记录(内容生成后留存,可重新打开续编)
# ---------------------------------------------------------------------------
@router.post("/projects", response_model=BidProjectDetail)
def api_create_project(req: BidProjectSave) -> BidProjectDetail:
    return services.create_project(req)


@router.get("/projects", response_model=BidProjectList)
def api_list_projects() -> BidProjectList:
    return services.list_projects()


@router.get("/projects/{project_id}", response_model=BidProjectDetail)
def api_get_project(project_id: str) -> BidProjectDetail:
    try:
        return services.get_project(project_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"项目不存在:{project_id}") from e


@router.put("/projects/{project_id}", response_model=BidProjectDetail)
def api_update_project(project_id: str, req: BidProjectSave) -> BidProjectDetail:
    try:
        return services.update_project(project_id, req)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"项目不存在:{project_id}") from e


# ---------------------------------------------------------------------------
# 对话式 Agent(SSE 流式)
# ---------------------------------------------------------------------------
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.get("/chat/status", response_model=ChatStatusResponse)
def api_chat_status() -> ChatStatusResponse:
    return ChatStatusResponse(**chat_service.chat_status())


@router.post("/chat")
def api_chat(req: ChatRequest) -> StreamingResponse:
    """开启一轮对话,SSE 流式返回事件(thinking/tool_call/tool_result/await_confirm/message)。"""
    return StreamingResponse(
        chat_service.start_chat_stream(req.message),
        media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat/confirm")
def api_chat_confirm(req: ChatConfirmRequest) -> StreamingResponse:
    """对挂起的写操作确认/拒绝后,继续 SSE 流式推进。"""
    return StreamingResponse(
        chat_service.confirm_chat_stream(req.session_id, req.call_id, req.approved),
        media_type="text/event-stream", headers=_SSE_HEADERS)
