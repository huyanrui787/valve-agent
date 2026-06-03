"""标书偏离表引擎(对应方案 3.2 节,偏离判定逻辑)。

体现"规则保准确 + 模型保表达":偏离判定是确定的比较运算,带证据链;
建议话术可由 LLM 润色(此处给规则化默认话术,LLM 层可覆盖)。

判定:
  满足   —— 产品能力覆盖要求
  正偏离 —— 产品优于要求(加分项)
  负偏离 —— 产品不达标(红色高亮 + 替代建议 + 话术)
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from ..models import CompareOp, Product, TenderRequirement


class Verdict(str, Enum):
    SATISFY = "满足"
    POSITIVE = "正偏离"
    NEGATIVE = "负偏离"
    UNKNOWN = "待确认"


class DeviationItem(BaseModel):
    """偏离表的一行。"""

    seq: int
    param: str
    requirement: str  # 招标要求(可读)
    product_capability: str  # 产品能力(可读)
    verdict: Verdict
    is_critical: bool = False
    evidence: list[str] = Field(default_factory=list, description="证据链")
    suggestion: str = ""  # 负偏离时的建议话术/替代方案


class DeviationTable(BaseModel):
    """完整技术偏离表。"""

    product_code: str
    product_name: str
    items: list[DeviationItem]

    @property
    def negative_count(self) -> int:
        return sum(1 for i in self.items if i.verdict is Verdict.NEGATIVE)

    @property
    def positive_count(self) -> int:
        return sum(1 for i in self.items if i.verdict is Verdict.POSITIVE)

    @property
    def critical_negatives(self) -> list[DeviationItem]:
        return [i for i in self.items if i.verdict is Verdict.NEGATIVE and i.is_critical]


# 参数名 → 从 Product 提取 (能力数值/能力描述, higher_is_better) 的方式。
# 数值型参数返回 (lower_bound, upper_bound);文本/集合型走另一路径。
class BidComplianceEngine:
    """技术偏离表引擎。"""

    def assess(
        self, product: Product, requirements: list[TenderRequirement],
        chosen_body: str | None = None,
    ) -> DeviationTable:
        items: list[DeviationItem] = []
        for idx, req in enumerate(requirements, start=1):
            items.append(self._assess_one(idx, product, req, chosen_body))
        return DeviationTable(
            product_code=product.code, product_name=product.name, items=items
        )

    # ------------------------------------------------------------------
    def _assess_one(
        self, seq: int, p: Product, req: TenderRequirement, chosen_body: str | None,
    ) -> DeviationItem:
        param = req.param

        if param in ("公称压力", "PN", "压力"):
            return self._numeric(seq, req, cap_low=p.pn_range.min_pn,
                                  cap_high=p.pn_range.max_pn, cap_unit="bar",
                                  evidence=[f"产品库:{p.code} PN{p.pn_range.min_pn:g}"
                                            f"-{p.pn_range.max_pn:g}"])
        if param in ("公称通径", "DN", "通径"):
            return self._numeric(seq, req, cap_low=p.dn_range.min_dn,
                                  cap_high=p.dn_range.max_dn, cap_unit="mm",
                                  evidence=[f"产品库:{p.code} DN{p.dn_range.min_dn}"
                                            f"-{p.dn_range.max_dn}"])
        if param in ("工作温度", "温度", "适用温度"):
            return self._numeric(seq, req, cap_low=p.temp_range.min_c,
                                  cap_high=p.temp_range.max_c, cap_unit="℃",
                                  evidence=[f"产品库:{p.code} 适用 "
                                            f"{p.temp_range.min_c:g}~{p.temp_range.max_c:g}℃"])
        if param in ("执行标准", "标准"):
            caps = [s.value for s in p.standards]
            return self._membership(seq, req, caps,
                                    evidence=[f"产品库:{p.code} 执行 {'/'.join(caps)}"])
        if param in ("阀体材质", "材质"):
            caps = list(p.body_materials) if not chosen_body else [chosen_body] + p.body_materials
            return self._membership(seq, req, caps,
                                    evidence=[f"产品库:{p.code} 阀体可选 "
                                              f"{'/'.join(p.body_materials)}"])
        if param in ("驱动方式", "驱动"):
            caps = [d.value for d in p.drives]
            return self._membership(seq, req, caps,
                                    evidence=[f"产品库:{p.code} 驱动 {'/'.join(caps)}"])
        if param in ("连接方式", "连接"):
            caps = [c.value for c in p.connections]
            return self._membership(seq, req, caps,
                                    evidence=[f"产品库:{p.code} 连接 {'/'.join(caps)}"])

        # 未知参数:待确认
        return DeviationItem(
            seq=seq, param=param, requirement=req.raw or self._req_text(req),
            product_capability="(产品库无对应字段)", verdict=Verdict.UNKNOWN,
            is_critical=req.is_critical,
            evidence=["该参数未映射到产品库字段,需工程师人工确认"],
            suggestion="请人工核对该项要求并补充应答",
        )

    def _numeric(
        self, seq: int, req: TenderRequirement, cap_low: float, cap_high: float,
        cap_unit: str, evidence: list[str],
    ) -> DeviationItem:
        target = req.target_value
        cap_text = f"{cap_low:g}~{cap_high:g}{cap_unit}"
        req_text = self._req_text(req)
        verdict = Verdict.UNKNOWN
        suggestion = ""

        if target is None:
            verdict = Verdict.UNKNOWN
        elif req.op in (CompareOp.GE, CompareOp.GT):
            # 要求 >= target:产品上限需达到 target;高于则正偏离
            meets = cap_high >= target if req.op is CompareOp.GE else cap_high > target
            if meets:
                verdict = Verdict.POSITIVE if cap_high > target else Verdict.SATISFY
            else:
                verdict = Verdict.NEGATIVE
                suggestion = (f"本型号上限 {cap_high:g}{cap_unit} 低于要求 "
                              f"{target:g}{cap_unit},建议改选更高等级型号或确认工况")
        elif req.op in (CompareOp.LE, CompareOp.LT):
            meets = cap_low <= target if req.op is CompareOp.LE else cap_low < target
            verdict = Verdict.SATISFY if meets else Verdict.NEGATIVE
            if not meets:
                suggestion = f"本型号下限 {cap_low:g}{cap_unit} 高于要求 {target:g}{cap_unit}"
        elif req.op is CompareOp.EQ:
            verdict = Verdict.SATISFY if cap_low <= target <= cap_high else Verdict.NEGATIVE
            if verdict is Verdict.NEGATIVE:
                suggestion = f"要求精确 {target:g}{cap_unit},超出本型号 {cap_text}"

        ev = list(evidence)
        ev.append(f"判定依据:要求 {req_text},产品能力 {cap_text}")
        return DeviationItem(
            seq=seq, param=req.param, requirement=req_text, product_capability=cap_text,
            verdict=verdict, is_critical=req.is_critical, evidence=ev, suggestion=suggestion,
        )

    def _membership(
        self, seq: int, req: TenderRequirement, caps: list[str], evidence: list[str],
    ) -> DeviationItem:
        req_text = self._req_text(req)
        targets: list[str] = []
        if req.target_set:
            targets = req.target_set
        elif req.target_text:
            targets = [req.target_text]

        cap_text = "/".join(caps)
        if not targets:
            verdict = Verdict.UNKNOWN
            suggestion = "要求值缺失,需人工确认"
        else:
            hit = any(self._text_match(t, caps) for t in targets)
            verdict = Verdict.SATISFY if hit else Verdict.NEGATIVE
            suggestion = "" if hit else (
                f"要求 {'/'.join(targets)},本型号提供 {cap_text},"
                f"建议确认是否有满足该要求的同系列型号"
            )
        ev = list(evidence)
        ev.append(f"判定依据:要求 {req_text},产品能力 {cap_text}")
        return DeviationItem(
            seq=seq, param=req.param, requirement=req_text, product_capability=cap_text,
            verdict=verdict, is_critical=req.is_critical, evidence=ev, suggestion=suggestion,
        )

    @staticmethod
    def _text_match(target: str, caps: list[str]) -> bool:
        t = target.strip().upper()
        for c in caps:
            cu = c.upper()
            if t in cu or cu in t:
                return True
        return False

    @staticmethod
    def _req_text(req: TenderRequirement) -> str:
        if req.target_value is not None:
            return f"{req.param} {req.op.value} {req.target_value:g}{req.unit}".strip()
        if req.target_set:
            return f"{req.param} ∈ {{{', '.join(req.target_set)}}}"
        if req.target_text:
            return f"{req.param}: {req.target_text}"
        return req.param
