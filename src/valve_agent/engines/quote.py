"""报价成本引擎(对应方案 4.3 节,报价成本模型)。

体现"规则保准确":成本核算是确定的算式,带完整拆解与毛利率。

  单台成本 = Σ(物料量 × 材料单价) + 加工 + 表面处理 + 试验检测 + 包装运输
  含税单价 = 单台成本 ÷ (1 − 目标毛利率) × (1 + 税率) × 批量折扣 × 客户折扣
  出口报价 = 含税单价 × 汇率 + 出口附加费
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..knowledge import KnowledgeBase
from ..models import Product


class CostLine(BaseModel):
    """成本拆解中的一行。"""

    name: str
    material_key: str | None = None
    quantity: float = 0.0
    unit: str = ""
    unit_price: float = 0.0
    amount: float = 0.0
    note: str = ""


class QuoteLine(BaseModel):
    """单个型号的报价结果(含成本拆解)。"""

    product_code: str
    product_name: str
    dn: int
    pn_bar: float
    body_material: str
    trim_material: str
    quantity: int = 1

    cost_lines: list[CostLine] = Field(default_factory=list)
    material_cost: float = 0.0
    processing_cost: float = 0.0
    overhead: float = 0.0
    unit_cost: float = 0.0  # 单台总成本

    margin: float = 0.0  # 实际毛利率
    pre_tax_unit_price: float = 0.0
    unit_price: float = 0.0  # 含税单价(内销)
    export_unit_price_cny: float = 0.0  # 出口报价(折回 CNY,含附加费)
    line_total: float = 0.0  # 含税单价 × 数量

    price_basis: date | None = None
    warnings: list[str] = Field(default_factory=list)


class Quotation(BaseModel):
    """整单报价。"""

    customer: str = ""
    customer_tier: str = "C"
    is_export: bool = False
    price_basis: date | None = None
    lines: list[QuoteLine] = Field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(l.line_total for l in self.lines)

    @property
    def total_cost(self) -> float:
        return sum(l.unit_cost * l.quantity for l in self.lines)

    @property
    def overall_margin(self) -> float:
        rev_pretax = sum(l.pre_tax_unit_price * l.quantity for l in self.lines)
        if rev_pretax <= 0:
            return 0.0
        return (rev_pretax - self.total_cost) / rev_pretax


# 价格过期阈值(天):材料价格超过该天数未更新则预警
PRICE_STALE_DAYS = 180


class QuoteEngine:
    """报价成本引擎。"""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def quote_line(
        self,
        product: Product,
        dn: int,
        body_material: str,
        trim_material: str,
        quantity: int = 1,
        customer_tier: str = "C",
        is_export: bool = False,
        price_basis: date | None = None,
        target_margin: float | None = None,
    ) -> QuoteLine:
        basis = price_basis or date.today()
        policy = self.kb.pricing_policy
        margin = target_margin if target_margin is not None else policy.target_margin

        bom = self.kb.get_bom(product.bom_template_id)
        if bom is None:
            raise ValueError(f"型号 {product.code} 无 BOM 模板 {product.bom_template_id}")

        cost_lines: list[CostLine] = []
        material_cost = 0.0
        processing_cost = 0.0
        warnings: list[str] = []

        for line in bom.lines:
            if line.material_key:
                qty = line.quantity_for(dn)
                # 阀体/阀芯材质用选型确定的材质覆盖 BOM 默认键
                mat_key = self._resolve_material(line, body_material, trim_material)
                mp = self.kb.price_on(mat_key, basis)
                if mp is None:
                    warnings.append(f"材料 {mat_key} 无 {basis} 前的价格,按 0 计")
                    unit_price = 0.0
                else:
                    unit_price = mp.unit_price
                    latest = self.kb.latest_price_date(mat_key)
                    if latest and (basis - latest).days > PRICE_STALE_DAYS:
                        warnings.append(
                            f"材料 {mat_key} 价格已 {(basis - latest).days} 天未更新,建议复核"
                        )
                amount = qty * unit_price
                material_cost += amount
                cost_lines.append(
                    CostLine(name=line.name, material_key=mat_key, quantity=round(qty, 3),
                             unit=line.unit, unit_price=unit_price, amount=round(amount, 2))
                )
            else:
                processing_cost += line.fixed_cost
                cost_lines.append(
                    CostLine(name=line.name, quantity=1, unit="项",
                             unit_price=line.fixed_cost, amount=line.fixed_cost,
                             note="固定费用")
                )

        overhead = material_cost * policy.processing_overhead
        cost_lines.append(
            CostLine(name="间接费(管理/加工加成)", quantity=1, unit="项",
                     unit_price=round(overhead, 2), amount=round(overhead, 2),
                     note=f"材料成本 × {policy.processing_overhead:.0%}")
        )
        unit_cost = material_cost + processing_cost + overhead

        # ---- 定价 ----
        if not 0 < margin < 1:
            raise ValueError("目标毛利率必须在 (0,1) 之间")
        pre_tax = unit_cost / (1 - margin)
        vol_factor = policy.volume_factor(quantity)
        tier_factor = policy.tier_factor(customer_tier)
        pre_tax_adj = pre_tax * vol_factor * tier_factor
        unit_price = pre_tax_adj * (1 + policy.tax_rate)
        actual_margin = (pre_tax_adj - unit_cost) / pre_tax_adj if pre_tax_adj else 0.0

        export_cny = 0.0
        if is_export:
            # 出口通常不含内销增值税口径,这里用税前价折汇 + 附加费
            export_cny = pre_tax_adj + policy.export_surcharge

        if actual_margin < 0.05:
            warnings.append(f"折扣后实际毛利仅 {actual_margin:.1%},接近成本线,请复核")

        return QuoteLine(
            product_code=product.code,
            product_name=product.name,
            dn=dn,
            pn_bar=0.0,
            body_material=body_material,
            trim_material=trim_material,
            quantity=quantity,
            cost_lines=cost_lines,
            material_cost=round(material_cost, 2),
            processing_cost=round(processing_cost, 2),
            overhead=round(overhead, 2),
            unit_cost=round(unit_cost, 2),
            margin=round(actual_margin, 4),
            pre_tax_unit_price=round(pre_tax_adj, 2),
            unit_price=round(unit_price, 2),
            export_unit_price_cny=round(export_cny, 2),
            line_total=round(unit_price * quantity, 2),
            price_basis=basis,
            warnings=warnings,
        )

    def _resolve_material(self, line, body_material: str, trim_material: str) -> str:
        """阀体行用选定阀体材质,阀芯/阀座/阀杆/球体等用选定阀芯材质。"""
        body_parts = ("阀体",)
        trim_parts = ("球体", "闸板", "阀瓣", "阀座", "阀杆", "蝶板")
        if any(k in line.name for k in body_parts):
            return body_material
        if any(k in line.name for k in trim_parts):
            return trim_material
        return line.material_key
