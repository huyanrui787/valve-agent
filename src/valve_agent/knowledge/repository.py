"""企业知识底座 —— 内存仓库实现。

KnowledgeBase 聚合六大库:产品选型库 / 价格成本库 / 材质规则 /
资质证照库 / 历史业绩库 / BOM 模板。两个 Agent 共用同一实例
(对应方案"底座先行、一次确定两处复用")。

生产环境会替换为关系库 + 向量库 + 对象存储,这里用内存结构保证
确定性核心可独立运行与测试。
"""

from __future__ import annotations

from datetime import date

from ..models import (
    BomTemplate,
    MaterialPrice,
    MaterialRule,
    PricingPolicy,
    Product,
    Qualification,
    TrackRecord,
)
from ..models.enums import Medium


class KnowledgeBase:
    """六大知识库的统一内存仓库。"""

    def __init__(self) -> None:
        self.products: dict[str, Product] = {}
        self.bom_templates: dict[str, BomTemplate] = {}
        self.material_rules: list[MaterialRule] = []
        # 价格按 material_key 存时间序列(升序)
        self._prices: dict[str, list[MaterialPrice]] = {}
        self.qualifications: list[Qualification] = []
        self.track_records: list[TrackRecord] = []
        self.pricing_policy = PricingPolicy()

    # ---- 产品 ----
    def add_product(self, p: Product) -> None:
        self.products[p.code] = p

    def add_bom(self, b: BomTemplate) -> None:
        self.bom_templates[b.id] = b

    def get_bom(self, template_id: str) -> BomTemplate | None:
        return self.bom_templates.get(template_id)

    def active_products(self) -> list[Product]:
        return [p for p in self.products.values() if p.active]

    # ---- 材质规则 ----
    def add_material_rule(self, r: MaterialRule) -> None:
        self.material_rules.append(r)

    def allowed_materials(
        self, medium: Medium, temp_c: float, pn_bar: float
    ) -> tuple[set[str], set[str], list[str]]:
        """返回 (允许阀体材质, 允许阀芯材质, 命中的规则说明)。

        若无规则命中,返回空集合表示"无约束"(由调用方决定是否放行)。
        多条规则命中时取并集(任一规则允许即允许)。
        """
        body: set[str] = set()
        trim: set[str] = set()
        notes: list[str] = []
        for r in self.material_rules:
            if r.applies(medium, temp_c, pn_bar):
                body |= set(r.allowed_body_materials)
                trim |= set(r.allowed_trim_materials)
                if r.note:
                    notes.append(r.note)
        return body, trim, notes

    # ---- 价格(版本化) ----
    def add_price(self, mp: MaterialPrice) -> None:
        series = self._prices.setdefault(mp.material_key, [])
        series.append(mp)
        series.sort(key=lambda x: x.effective_date)

    def price_on(self, material_key: str, basis: date) -> MaterialPrice | None:
        """取报价基准日 basis 当日有效(effective_date <= basis)的最新价格。"""
        series = self._prices.get(material_key)
        if not series:
            return None
        valid = [p for p in series if p.effective_date <= basis]
        return valid[-1] if valid else None

    def latest_price_date(self, material_key: str) -> date | None:
        series = self._prices.get(material_key)
        return series[-1].effective_date if series else None

    # ---- 资质 ----
    def add_qualification(self, q: Qualification) -> None:
        self.qualifications.append(q)

    # ---- 业绩 ----
    def add_track_record(self, t: TrackRecord) -> None:
        self.track_records.append(t)
