"""价格成本库与商务实体。

MaterialPrice  —— 版本化材料单价(按生效日期存时间序列,对应方案 2.3 价格版本化)
PricingPolicy  —— 毛利率/折扣/税率/汇率等定价参数
Qualification  —— 资质证照(含有效期)
TrackRecord    —— 历史业绩/合同
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class MaterialPrice(BaseModel):
    """某材料在某生效日期起的单价。

    价格库保存时间序列:报价时锁定"报价基准日",取 <= 基准日的最新一条,
    避免材料价格波动导致的口径漂移。
    """

    material_key: str
    name: str
    unit: str = "kg"
    unit_price: float = Field(description="单价,元/单位")
    effective_date: date
    source: str = ""


class PricingPolicy(BaseModel):
    """定价策略参数(对应方案 4.3 报价成本模型)。"""

    target_margin: float = Field(0.30, description="目标毛利率,0~1")
    tax_rate: float = Field(0.13, description="增值税率")
    customer_tier_discount: dict[str, float] = Field(
        default_factory=lambda: {"A": 0.95, "B": 0.98, "C": 1.0},
        description="客户等级 → 折扣系数",
    )
    volume_discounts: list[tuple[int, float]] = Field(
        default_factory=lambda: [(1, 1.0), (10, 0.97), (50, 0.93), (100, 0.90)],
        description="批量阶梯 (起订量, 折扣系数),按起订量降序匹配",
    )
    processing_overhead: float = Field(
        0.15, description="加工/管理间接费率,基于材料成本加成"
    )
    export_fx_rate: float = Field(7.20, description="出口汇率 CNY/USD")
    export_surcharge: float = Field(0.0, description="出口附加费(海运/认证),元/台")

    def volume_factor(self, qty: int) -> float:
        factor = 1.0
        for moq, f in sorted(self.volume_discounts, key=lambda x: x[0]):
            if qty >= moq:
                factor = f
        return factor

    def tier_factor(self, tier: str) -> float:
        return self.customer_tier_discount.get(tier, 1.0)


class Qualification(BaseModel):
    """资质证照(对应资质证照库)。"""

    name: str
    category: str = Field(description="如 ISO9001 / API607 / 型式试验报告")
    issuer: str = ""
    cert_no: str = ""
    valid_until: date | None = None

    def is_valid_on(self, on: date) -> bool:
        return self.valid_until is None or self.valid_until >= on


class TrackRecord(BaseModel):
    """历史业绩/合同(对应历史业绩库)。"""

    project_name: str
    customer: str
    industry: str = ""
    valve_type: str = ""
    contract_date: date
    amount: float = 0.0
    summary: str = ""
