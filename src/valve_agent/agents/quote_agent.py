"""智能报价 Agent(产品二的编排层)。

把"选型引擎 → BOM成本核算 → 毛利定价"串成端到端能力,并支持:
  - 自然语言/参数化选型(经 ConditionParser)
  - 批量询价单逐行处理
  - 历史报价参考(从业绩库做相似提示)

体现方案"规则保准确、模型保表达":硬逻辑全走引擎,LLM 仅用于文字表达。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..engines import (
    Quotation,
    QuoteEngine,
    QuoteLine,
    RankStrategy,
    SelectionEngine,
    SelectionResult,
)
from ..knowledge import KnowledgeBase
from ..llm import ConditionParser, LLMProvider, OfflineProvider
from ..models import WorkingCondition


class QuoteRequestLine(BaseModel):
    """批量询价的一行(自然语言或结构化工况二选一)。"""

    text: str | None = None
    condition: WorkingCondition | None = None
    quantity: int = 1


class LineOutcome(BaseModel):
    """单行询价的处理结果。"""

    input_text: str
    quantity: int
    selection: SelectionResult | None = None
    quote: QuoteLine | None = None
    error: str | None = None
    history_hint: str = ""


class QuoteAgent:
    """智能报价 Agent。"""

    def __init__(self, kb: KnowledgeBase, llm: LLMProvider | None = None) -> None:
        self.kb = kb
        self.selector = SelectionEngine(kb)
        self.quoter = QuoteEngine(kb)
        self.parser = ConditionParser()
        self.llm = llm or OfflineProvider()

    def quote_condition(
        self,
        cond: WorkingCondition,
        quantity: int = 1,
        customer_tier: str = "C",
        is_export: bool = False,
        price_basis: date | None = None,
        strategy: RankStrategy = RankStrategy.COST,
    ) -> LineOutcome:
        sel = self.selector.select(cond, strategy=strategy)
        text = self._cond_text(cond)
        if sel.best is None:
            return LineOutcome(
                input_text=text, quantity=quantity, selection=sel,
                error="无匹配型号,请放宽工况或补充非标定制需求")
        best = sel.best
        ql = self.quoter.quote_line(
            best.product, cond.dn, best.chosen_body_material,
            best.chosen_trim_material, quantity=quantity,
            customer_tier=customer_tier, is_export=is_export, price_basis=price_basis)
        ql.pn_bar = cond.pn_bar
        return LineOutcome(
            input_text=text, quantity=quantity, selection=sel, quote=ql,
            history_hint=self._history_hint(best.product.valve_type.value))

    def quote_text(self, text: str, quantity: int = 1, **kw) -> LineOutcome:
        try:
            cond = self.parser.parse(text)
        except ValueError as e:
            return LineOutcome(input_text=text, quantity=quantity, error=str(e))
        return self.quote_condition(cond, quantity=quantity, **kw)

    def quote_batch(
        self,
        lines: list[QuoteRequestLine],
        customer: str = "",
        customer_tier: str = "C",
        is_export: bool = False,
        price_basis: date | None = None,
    ) -> tuple[Quotation, list[LineOutcome]]:
        """批量询价单处理,返回整单报价 + 每行明细。"""
        outcomes: list[LineOutcome] = []
        quote = Quotation(customer=customer, customer_tier=customer_tier,
                          is_export=is_export, price_basis=price_basis or date.today())
        for rl in lines:
            if rl.condition is not None:
                oc = self.quote_condition(
                    rl.condition, quantity=rl.quantity, customer_tier=customer_tier,
                    is_export=is_export, price_basis=price_basis)
            elif rl.text:
                oc = self.quote_text(
                    rl.text, quantity=rl.quantity, customer_tier=customer_tier,
                    is_export=is_export, price_basis=price_basis)
            else:
                oc = LineOutcome(input_text="(空行)", quantity=rl.quantity,
                                 error="询价行缺少 text 或 condition")
            outcomes.append(oc)
            if oc.quote is not None:
                quote.lines.append(oc.quote)
        return quote, outcomes

    # ------------------------------------------------------------------
    def _history_hint(self, valve_type: str) -> str:
        matches = [r for r in self.kb.track_records if valve_type in r.valve_type]
        if not matches:
            return ""
        latest = max(matches, key=lambda r: r.contract_date)
        return (f"历史参考:{latest.contract_date} 「{latest.project_name}」"
                f"({latest.customer})含{valve_type},合同额约 {latest.amount/1e4:.0f} 万元")

    @staticmethod
    def _cond_text(c: WorkingCondition) -> str:
        parts = [f"DN{c.dn}", f"PN{c.pn_bar:g}", c.medium.value, f"{c.temp_c:g}℃"]
        if c.valve_type:
            parts.insert(0, c.valve_type.value)
        if c.drive:
            parts.append(c.drive.value)
        if c.body_material_pref:
            parts.append(c.body_material_pref)
        return " ".join(parts)
