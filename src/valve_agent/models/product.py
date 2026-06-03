"""产品选型库的核心实体(对应方案文档 2.2 节)。

Product       —— 阀门型号及其能力区间(DN/PN/材质/驱动/连接/介质/温度/标准)
MaterialRule  —— 介质+温度+压力 → 允许材质集合(剔除不合规组合)
BomTemplate   —— 型号 → 物料行 + 随 DN/PN 缩放的算量规则
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import (
    ConnectionType,
    DriveType,
    Medium,
    Standard,
    ValveType,
)


class DNRange(BaseModel):
    """公称通径区间(含端点),单位 mm。"""

    min_dn: int
    max_dn: int

    def contains(self, dn: int) -> bool:
        return self.min_dn <= dn <= self.max_dn


class PNRange(BaseModel):
    """公称压力区间(含端点),统一以 PN(bar)口径存储。"""

    min_pn: float
    max_pn: float

    def contains(self, pn_bar: float) -> bool:
        return self.min_pn <= pn_bar <= self.max_pn


class TempRange(BaseModel):
    """适用温度区间(含端点),单位 ℃。"""

    min_c: float
    max_c: float

    def contains(self, c: float) -> bool:
        return self.min_c <= c <= self.max_c


class Product(BaseModel):
    """阀门产品型号。

    字段对应方案 2.2「产品型号(Product)」。能力以区间/集合表达,
    选型引擎据此做硬过滤与材质校验。
    """

    code: str = Field(description="型号编码,如 Q41F-16C")
    name: str
    valve_type: ValveType
    dn_range: DNRange
    pn_range: PNRange
    temp_range: TempRange
    body_materials: list[str] = Field(description="阀体可选材质集")
    trim_materials: list[str] = Field(description="阀芯/阀座可选材质集")
    seal_types: list[str] = Field(default_factory=list, description="密封型式")
    drives: list[DriveType]
    connections: list[ConnectionType]
    media: list[Medium] = Field(description="适用介质")
    standards: list[Standard]
    bom_template_id: str
    active: bool = True

    def supports_pn(self, pn_bar: float) -> bool:
        return self.pn_range.contains(pn_bar)

    def supports_dn(self, dn: int) -> bool:
        return self.dn_range.contains(dn)


class MaterialRule(BaseModel):
    """材质规则:在给定介质 + 温度区间 + 压力上限下,允许使用的材质集合。

    选型引擎用它剔除"介质+温度+压力"不允许的材质组合
    (如高温蒸汽禁用某些软密封)。
    """

    medium: Medium
    temp_range: TempRange
    max_pn: float = Field(description="该规则适用的压力上限(PN bar)")
    allowed_body_materials: list[str]
    allowed_trim_materials: list[str]
    note: str = ""

    def applies(self, medium: Medium, temp_c: float, pn_bar: float) -> bool:
        return (
            self.medium == medium
            and self.temp_range.contains(temp_c)
            and pn_bar <= self.max_pn
        )


class BomLine(BaseModel):
    """BOM 模板中的一行物料。

    qty_base + qty_per_dn 表达"随 DN 缩放"的算量规则:
        实际用量 = qty_base + qty_per_dn * DN
    material_key 关联到价格库的材料编码;若为空表示该行用固定加工/检测费。
    """

    name: str
    material_key: str | None = None
    qty_base: float = 0.0
    qty_per_dn: float = 0.0
    unit: str = "kg"
    fixed_cost: float = 0.0  # 非物料行(加工/检测/包装)的固定费用,单位元

    def quantity_for(self, dn: int) -> float:
        return self.qty_base + self.qty_per_dn * dn


class BomTemplate(BaseModel):
    """型号对应的 BOM 模板。"""

    id: str
    description: str = ""
    lines: list[BomLine]
