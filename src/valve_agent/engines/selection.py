"""选型规则引擎(对应方案 4.2 节,四步选型)。

体现"规则保准确":选型走确定性规则与精确查询,不依赖大模型臆测参数。
每个候选都带"选型依据"与"淘汰原因",便于人工复核(证据链)。

步骤:
  1. 硬过滤   —— DN/PN/介质/温度/(阀类/标准)从产品库筛候选
  2. 材质校验 —— 用材质规则剔除"介质+温度+压力"不允许的材质组合
  3. 驱动连接 —— 匹配驱动方式与连接方式
  4. 排序推荐 —— 按策略(成本最优/交期/历史成交)排序,返回 Top-N
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..knowledge import KnowledgeBase
from ..models import Product, WorkingCondition


class RankStrategy(str, Enum):
    COST = "成本最优"
    HISTORY = "历史成交优先"


class Rejection(BaseModel):
    """某型号被淘汰的记录。"""

    code: str
    name: str
    stage: str = Field(description="淘汰所在步骤")
    reason: str


class Candidate(BaseModel):
    """通过全部规则的候选型号。"""

    product: Product
    chosen_body_material: str
    chosen_trim_material: str
    reasons: list[str] = Field(default_factory=list, description="选型依据/证据链")
    score: float = 0.0

    model_config = {"arbitrary_types_allowed": True}


class SelectionResult(BaseModel):
    """选型引擎输出。"""

    condition: WorkingCondition
    candidates: list[Candidate]
    rejections: list[Rejection]
    material_notes: list[str] = Field(default_factory=list)

    @property
    def best(self) -> Candidate | None:
        return self.candidates[0] if self.candidates else None


class SelectionEngine:
    """四步阀门选型规则引擎。"""

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def select(
        self,
        cond: WorkingCondition,
        top_n: int = 3,
        strategy: RankStrategy = RankStrategy.COST,
    ) -> SelectionResult:
        rejections: list[Rejection] = []
        pn = cond.pn_bar

        # ---- 步骤 2 前置:取该工况允许的材质集合 ----
        allowed_body, allowed_trim, mat_notes = self.kb.allowed_materials(
            cond.medium, cond.temp_c, pn
        )

        candidates: list[Candidate] = []
        for p in self.kb.active_products():
            # ---- 步骤 1:硬过滤 ----
            if cond.valve_type is not None and p.valve_type != cond.valve_type:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"阀类不符:需要 {cond.valve_type.value}")
                )
                continue
            if not p.supports_dn(cond.dn):
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"通径超范围:DN{cond.dn} 不在 "
                                     f"DN{p.dn_range.min_dn}-{p.dn_range.max_dn}")
                )
                continue
            if not p.supports_pn(pn):
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"压力超范围:PN{pn:g} 不在 "
                                     f"PN{p.pn_range.min_pn:g}-{p.pn_range.max_pn:g}")
                )
                continue
            if cond.medium not in p.media:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"介质不适用:{cond.medium.value}")
                )
                continue
            if not p.temp_range.contains(cond.temp_c):
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"温度超范围:{cond.temp_c:g}℃ 不在 "
                                     f"{p.temp_range.min_c:g}~{p.temp_range.max_c:g}℃")
                )
                continue
            if cond.standard is not None and cond.standard not in p.standards:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="硬过滤",
                              reason=f"标准不符:需要 {cond.standard.value}")
                )
                continue

            # ---- 步骤 2:材质校验 ----
            body_opts = list(p.body_materials)
            trim_opts = list(p.trim_materials)
            if allowed_body:
                body_opts = [m for m in body_opts if m in allowed_body]
            if allowed_trim:
                trim_opts = [m for m in trim_opts if m in allowed_trim]
            if not body_opts or not trim_opts:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="材质校验",
                              reason=f"无满足"
                                     f"{cond.medium.value}@{cond.temp_c:g}℃ 的材质组合")
                )
                continue
            # 材质偏好
            chosen_body = self._pick_material(body_opts, cond.body_material_pref)
            chosen_trim = trim_opts[0]

            # ---- 步骤 3:驱动 & 连接匹配 ----
            if cond.drive is not None and cond.drive not in p.drives:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="驱动连接",
                              reason=f"驱动方式不支持:{cond.drive.value}")
                )
                continue
            if cond.connection is not None and cond.connection not in p.connections:
                rejections.append(
                    Rejection(code=p.code, name=p.name, stage="驱动连接",
                              reason=f"连接方式不支持:{cond.connection.value}")
                )
                continue

            # ---- 通过:构建候选 + 证据链 ----
            reasons = self._build_reasons(p, cond, chosen_body, chosen_trim, mat_notes)
            candidates.append(
                Candidate(
                    product=p,
                    chosen_body_material=chosen_body,
                    chosen_trim_material=chosen_trim,
                    reasons=reasons,
                )
            )

        # ---- 步骤 4:排序 ----
        self._rank(candidates, cond, strategy)
        return SelectionResult(
            condition=cond,
            candidates=candidates[:top_n],
            rejections=rejections,
            material_notes=mat_notes,
        )

    # ------------------------------------------------------------------
    def _pick_material(self, options: list[str], pref: str | None) -> str:
        if pref and pref in options:
            return pref
        return options[0]

    def _build_reasons(
        self, p: Product, cond: WorkingCondition, body: str, trim: str,
        mat_notes: list[str],
    ) -> list[str]:
        reasons = [
            f"阀类 {p.valve_type.value} 满足要求",
            f"DN{cond.dn} 落在 DN{p.dn_range.min_dn}-{p.dn_range.max_dn}",
            f"PN{cond.pn_bar:g} 落在 PN{p.pn_range.min_pn:g}-{p.pn_range.max_pn:g}",
            f"{cond.medium.value}@{cond.temp_c:g}℃ 在适用范围内",
            f"选用阀体材质 {body}、阀芯/阀座材质 {trim}",
        ]
        if cond.drive:
            reasons.append(f"支持{cond.drive.value}驱动")
        if cond.connection:
            reasons.append(f"支持{cond.connection.value}连接")
        for n in mat_notes:
            reasons.append(f"材质规则:{n}")
        return reasons

    def _rank(
        self, candidates: list[Candidate], cond: WorkingCondition,
        strategy: RankStrategy,
    ) -> None:
        """打分排序。成本策略用粗略材料成本代理(避免循环依赖报价引擎)。"""
        from datetime import date

        basis = date.today()
        for c in candidates:
            # 用阀体材质单价作为成本代理(越低分越高)
            mp = self.kb.price_on(_material_key_of(c.chosen_body_material), basis)
            body_price = mp.unit_price if mp else 50.0
            cost_proxy = body_price * (1 + cond.dn / 100.0)
            if strategy is RankStrategy.COST:
                c.score = 10000.0 / (cost_proxy + 1)
            else:  # HISTORY
                hist = sum(
                    1 for r in self.kb.track_records
                    if c.product.valve_type.value in r.valve_type
                )
                c.score = hist * 100 + 10000.0 / (cost_proxy + 1)
        candidates.sort(key=lambda x: x.score, reverse=True)


def _material_key_of(material: str) -> str:
    """材质名 → 价格库 material_key(种子数据里二者一致)。"""
    return material
