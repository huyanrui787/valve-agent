"""废标自检 + 资质业绩匹配(对应方案 3.4 / 3.5 节)。

废标自检:对照废标清单逐项核查(资质有效期、关键项响应、关键废标条款),
         输出"废标风险体检报告"。
资质业绩匹配:按招标要求检索资质库/业绩库,组装匹配项。
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum

from pydantic import BaseModel, Field

from ..knowledge import KnowledgeBase
from ..models import Qualification, TrackRecord
from .compliance import DeviationTable, Verdict


class RiskLevel(str, Enum):
    OK = "通过"
    WARN = "预警"
    FAIL = "高风险"


class CheckItem(BaseModel):
    name: str
    level: RiskLevel
    detail: str


class ComplianceReport(BaseModel):
    """废标风险体检报告。"""

    items: list[CheckItem]
    bid_date: date

    @property
    def fails(self) -> list[CheckItem]:
        return [i for i in self.items if i.level is RiskLevel.FAIL]

    @property
    def warns(self) -> list[CheckItem]:
        return [i for i in self.items if i.level is RiskLevel.WARN]

    @property
    def overall(self) -> RiskLevel:
        if self.fails:
            return RiskLevel.FAIL
        if self.warns:
            return RiskLevel.WARN
        return RiskLevel.OK


# 资质有效期临近预警阈值(天)
CERT_EXPIRY_WARN_DAYS = 90


class WasteBidChecker:
    """废标自检器。"""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def check(
        self,
        bid_date: date,
        deviation_tables: list[DeviationTable] | None = None,
        required_qual_categories: list[str] | None = None,
        min_track_records: int = 0,
        industry: str | None = None,
    ) -> ComplianceReport:
        items: list[CheckItem] = []

        # 1. 资质有效期
        for q in self.kb.qualifications:
            if q.valid_until is None:
                continue
            if q.valid_until < bid_date:
                items.append(CheckItem(
                    name=f"资质有效期:{q.name}", level=RiskLevel.FAIL,
                    detail=f"已于 {q.valid_until} 过期,投标日 {bid_date},须更新"))
            elif q.valid_until <= bid_date + timedelta(days=CERT_EXPIRY_WARN_DAYS):
                items.append(CheckItem(
                    name=f"资质有效期:{q.name}", level=RiskLevel.WARN,
                    detail=f"{q.valid_until} 到期,临近投标后有效期,建议核实"))

        # 2. 要求的资质类目是否齐备
        if required_qual_categories:
            have = {q.category for q in self.kb.qualifications if q.is_valid_on(bid_date)}
            for cat in required_qual_categories:
                if cat not in have:
                    items.append(CheckItem(
                        name=f"资质齐备:{cat}", level=RiskLevel.FAIL,
                        detail=f"招标要求 {cat} 认证,资质库缺失或已过期"))
                else:
                    items.append(CheckItem(
                        name=f"资质齐备:{cat}", level=RiskLevel.OK,
                        detail="已具备且在有效期内"))

        # 3. 业绩数量
        if min_track_records > 0:
            matched = self._match_records(industry)
            if len(matched) < min_track_records:
                items.append(CheckItem(
                    name="业绩数量", level=RiskLevel.FAIL,
                    detail=f"要求近似业绩 ≥{min_track_records} 项,"
                           f"匹配到 {len(matched)} 项"))
            else:
                items.append(CheckItem(
                    name="业绩数量", level=RiskLevel.OK,
                    detail=f"要求 ≥{min_track_records} 项,匹配 {len(matched)} 项"))

        # 4. 关键项负偏离(可能废标)
        if deviation_tables:
            for dt in deviation_tables:
                crit = dt.critical_negatives
                if crit:
                    params = ", ".join(i.param for i in crit)
                    items.append(CheckItem(
                        name=f"关键技术响应:{dt.product_code}", level=RiskLevel.FAIL,
                        detail=f"关键项负偏离({params}),极可能废标,须改型或澄清"))
                neg = dt.negative_count
                if neg and not crit:
                    items.append(CheckItem(
                        name=f"技术响应:{dt.product_code}", level=RiskLevel.WARN,
                        detail=f"存在 {neg} 项非关键负偏离,建议补充偏离说明"))

        # 5. 通用格式提示(规则化清单)
        items.append(CheckItem(
            name="签字盖章", level=RiskLevel.WARN,
            detail="请确认投标函、法人授权、报价表等均已签字并加盖公章(需人工核验)"))

        return ComplianceReport(items=items, bid_date=bid_date)

    def _match_records(self, industry: str | None) -> list[TrackRecord]:
        if not industry:
            return list(self.kb.track_records)
        return [r for r in self.kb.track_records if industry in r.industry]


class QualificationMatcher:
    """资质业绩智能匹配(对应方案 3.5)。"""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def match_qualifications(
        self, required_categories: list[str], on: date
    ) -> dict[str, Qualification | None]:
        out: dict[str, Qualification | None] = {}
        for cat in required_categories:
            found = next(
                (q for q in self.kb.qualifications
                 if q.category == cat and q.is_valid_on(on)), None)
            out[cat] = found
        return out

    def match_records(
        self, industry: str | None = None, valve_type: str | None = None,
        recent_years: int | None = None, on: date | None = None,
    ) -> list[TrackRecord]:
        on = on or date.today()
        out = []
        for r in self.kb.track_records:
            if industry and industry not in r.industry:
                continue
            if valve_type and valve_type not in r.valve_type:
                continue
            if recent_years is not None:
                if (on - r.contract_date).days > recent_years * 365:
                    continue
            out.append(r)
        out.sort(key=lambda r: r.contract_date, reverse=True)
        return out
