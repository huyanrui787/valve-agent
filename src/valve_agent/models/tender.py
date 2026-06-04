"""招标文件解析产物模型。"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .request import TenderRequirement


class RiskItem(BaseModel):
    """废标/风险条款一条。"""

    clause: str
    level: str = Field(description="高/中/低")
    summary: str = ""


class TenderBrief(BaseModel):
    """招标要点清单(解析摘要)。"""

    title: str = ""
    bid_deadline: date | None = None
    required_qual_categories: list[str] = Field(default_factory=list)
    min_track_records: int = 0
    industry_hint: str = ""
    key_points: list[str] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)


class ParsedTender(BaseModel):
    """招标文件解析结果。"""

    source: str = ""
    raw_text: str = ""
    brief: TenderBrief = Field(default_factory=TenderBrief)
    requirements: list[TenderRequirement] = Field(default_factory=list)
    waste_clauses: list[str] = Field(default_factory=list, description="废标相关原文摘录")
