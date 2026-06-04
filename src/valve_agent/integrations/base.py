"""ERP / CRM 集成协议(可替换实现)。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..agents.bid_agent import BidPackage
from ..engines import Quotation


class SyncResult(BaseModel):
    """同步结果。"""

    ok: bool
    external_id: str = ""
    message: str = ""
    payload_path: str = ""


@runtime_checkable
class CRMClient(Protocol):
    """客户关系系统:报价回填。"""

    name: str

    def push_quotation(self, quote: Quotation, *, customer: str = "") -> SyncResult: ...


@runtime_checkable
class ERPClient(Protocol):
    """企业资源计划:成本/BOM 同步。"""

    name: str

    def push_quotation_cost(self, quote: Quotation, *, project_code: str = "") -> SyncResult: ...
    def push_bid_snapshot(self, package: BidPackage, *, project_code: str = "") -> SyncResult: ...
