"""工具注册表 —— 把确定性引擎包装成 Agent 可调用的工具(Engines as Tools)。

设计要点(对应方案 12.3):
  - 每个工具背后是一个确定性引擎,LLM 只填"意图参数"(选什么/几台/什么客户),
    所有价格与判定由引擎算出后回喂。LLM 永远不碰运算 —— "规则保准确"不变。
  - 工具分只读 / 写两类。写工具(导出/同步)由运行时的确认门拦截,
    用户放行后才真正执行(对应方案 12.7 人在环上)。
  - 工具声明用 OpenAI 风格 JSON Schema,供 function calling 使用。

工具复用现有 QuoteAgent / BidAgent 的能力,不重复引擎逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from ..agents import BidAgent, QuoteAgent
from ..knowledge import KnowledgeBase
from ..llm import ConditionParser
from ..models import CompareOp, TenderRequirement


@dataclass
class Tool:
    """一个可被 LLM 调用的工具。"""

    name: str
    description: str
    parameters: dict          # JSON Schema(OpenAI function.parameters)
    handler: Callable[..., Any]
    is_write: bool = False    # 写操作需经确认门

    def schema(self) -> dict:
        """OpenAI 风格的工具声明。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, arguments: dict) -> Any:
        return self.handler(**arguments)


class ToolRegistry:
    """工具集合:注册、取声明列表、按名执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)


# ---------------------------------------------------------------------------
# JSON Schema 片段
# ---------------------------------------------------------------------------
_SPEC_PROP = {
    "spec": {
        "type": "string",
        "description": '阀门工况自然语言描述,如 "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"。'
                       "必须包含通径(DN)与压力(PN 或 Class)。",
    }
}

_REQUIREMENTS_PROP = {
    "requirements": {
        "type": "array",
        "description": "招标技术要求清单。每条含参数名、比较符、目标值。",
        "items": {
            "type": "object",
            "properties": {
                "param": {"type": "string",
                          "description": "参数名:公称压力/公称通径/工作温度/执行标准/阀体材质/驱动方式/连接方式"},
                "op": {"type": "string", "enum": [">=", "<=", "==", ">", "<", "in"],
                       "description": "比较符;集合类要求用 in"},
                "target_value": {"type": "number", "description": "数值型目标值(压力/通径/温度)"},
                "target_set": {"type": "array", "items": {"type": "string"},
                               "description": "op=in 时的可选集合,如 [\"API\"] 或 [\"316\"]"},
                "unit": {"type": "string", "description": "单位,如 bar/mm/℃"},
                "is_critical": {"type": "boolean", "description": "是否关键项(负偏离可能废标)"},
            },
            "required": ["param", "op"],
        },
    }
}


def _build_requirements(raw: list[dict] | None) -> list[TenderRequirement]:
    """把工具入参里的 requirements 列表转成 TenderRequirement。"""
    out: list[TenderRequirement] = []
    for r in raw or []:
        out.append(TenderRequirement(
            param=r["param"],
            op=CompareOp(r.get("op", "in")),
            target_value=r.get("target_value"),
            target_set=r.get("target_set"),
            unit=r.get("unit", ""),
            is_critical=bool(r.get("is_critical", False)),
        ))
    return out


# ---------------------------------------------------------------------------
# 默认工具集:把 8 个引擎能力注册成工具
# ---------------------------------------------------------------------------
def build_default_registry(
    kb: KnowledgeBase,
    *,
    quote_agent: QuoteAgent | None = None,
    bid_agent: BidAgent | None = None,
    sync_dir: str = "./sync",
) -> ToolRegistry:
    """构建默认工具注册表。复用 QuoteAgent / BidAgent,不重复引擎逻辑。"""
    qa = quote_agent or QuoteAgent(kb)
    ba = bid_agent or BidAgent(kb)
    parser = ConditionParser()
    reg = ToolRegistry()

    # ---- 只读:选型 ----
    def _select_valve(spec: str, top_n: int = 3) -> dict:
        cond = parser.parse(spec)
        sel = qa.selector.select(cond, top_n=top_n)
        return {
            "condition": f"DN{cond.dn} PN{cond.pn_bar:g} {cond.medium.value} {cond.temp_c:g}℃",
            "candidates": [
                {"rank": i + 1, "code": c.product.code, "name": c.product.name,
                 "body_material": c.chosen_body_material,
                 "trim_material": c.chosen_trim_material,
                 "reasons": c.reasons[:4]}
                for i, c in enumerate(sel.candidates)
            ],
            "rejected_count": len(sel.rejections),
            "material_notes": sel.material_notes,
        }

    reg.register(Tool(
        name="select_valve",
        description="按工况选型:四步规则引擎返回候选型号(带选型依据)。用于回答'选什么阀门'。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP,
                                   "top_n": {"type": "integer", "description": "返回候选数,默认3"}},
                    "required": ["spec"]},
        handler=_select_valve,
    ))

    # ---- 只读:报价 ----
    def _quote(spec: str, quantity: int = 1, customer_tier: str = "C",
               is_export: bool = False) -> dict:
        oc = qa.quote_text(spec, quantity=quantity, customer_tier=customer_tier,
                           is_export=is_export)
        if oc.quote is None:
            return {"error": oc.error or "无匹配型号"}
        q = oc.quote
        return {
            "product_code": q.product_code, "product_name": q.product_name,
            "dn": q.dn, "quantity": q.quantity,
            "unit_cost": q.unit_cost, "unit_price": q.unit_price,
            "margin": q.margin, "line_total": q.line_total,
            "export_unit_price_cny": q.export_unit_price_cny,
            "warnings": q.warnings, "history_hint": oc.history_hint,
        }

    reg.register(Tool(
        name="quote",
        description="按工况选型并核算报价:BOM 成本拆解 + 毛利定价。用于回答'报多少钱'。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP,
                                   "quantity": {"type": "integer", "description": "数量,默认1"},
                                   "customer_tier": {"type": "string", "enum": ["A", "B", "C"],
                                                     "description": "客户等级,默认C"},
                                   "is_export": {"type": "boolean", "description": "是否出口报价"}},
                    "required": ["spec"]},
        handler=_quote,
    ))

    # ---- 只读:技术偏离表 ----
    def _assess_compliance(spec: str, requirements: list[dict] | None = None) -> dict:
        oc = qa.quote_text(spec, quantity=1)
        if oc.selection is None or oc.selection.best is None:
            return {"error": oc.error or "未选到型号"}
        best = oc.selection.best
        reqs = _build_requirements(requirements)
        dt = ba.compliance.assess(best.product, reqs, best.chosen_body_material)
        return {
            "product_code": dt.product_code, "product_name": dt.product_name,
            "items": [
                {"param": it.param, "requirement": it.requirement,
                 "capability": it.product_capability, "verdict": it.verdict.value,
                 "is_critical": it.is_critical, "suggestion": it.suggestion}
                for it in dt.items
            ],
            "negative_count": dt.negative_count,
            "critical_negative_count": len(dt.critical_negatives),
        }

    reg.register(Tool(
        name="assess_compliance",
        description="对选定型号逐条比对招标技术要求,生成偏离表(满足/正偏离/负偏离,关键负偏离预警)。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP, **_REQUIREMENTS_PROP},
                    "required": ["spec", "requirements"]},
        handler=_assess_compliance,
    ))

    # ---- 只读:废标自检 ----
    def _check_waste_bid(spec: str, requirements: list[dict] | None = None,
                         required_qual_categories: list[str] | None = None,
                         min_track_records: int = 0, industry: str = "") -> dict:
        oc = qa.quote_text(spec, quantity=1)
        if oc.selection is None or oc.selection.best is None:
            return {"error": oc.error or "未选到型号"}
        best = oc.selection.best
        reqs = _build_requirements(requirements)
        dt = ba.compliance.assess(best.product, reqs, best.chosen_body_material)
        report = ba.checker.check(
            bid_date=date.today(), deviation_tables=[dt],
            required_qual_categories=required_qual_categories,
            min_track_records=min_track_records, industry=industry or None)
        return {
            "overall": report.overall.value,
            "items": [{"name": it.name, "level": it.level.value, "detail": it.detail}
                      for it in report.items],
            "fail_count": len(report.fails), "warn_count": len(report.warns),
        }

    reg.register(Tool(
        name="check_waste_bid",
        description="废标风险体检:资质有效期、资质齐备、业绩数量、关键负偏离逐项核查,输出风险报告。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP, **_REQUIREMENTS_PROP,
                                   "required_qual_categories": {"type": "array",
                                       "items": {"type": "string"},
                                       "description": "招标要求的资质类目,如 [\"ISO9001\",\"API6D\"]"},
                                   "min_track_records": {"type": "integer",
                                       "description": "要求的最少近似业绩数"},
                                   "industry": {"type": "string", "description": "行业,用于业绩匹配"}},
                    "required": ["spec"]},
        handler=_check_waste_bid,
    ))

    # ---- 只读:RAG 检索 ----
    def _rag_search(query: str, kind: str = "", top_k: int = 5) -> dict:
        from ..rag import RagRetriever
        ret = RagRetriever(kb)
        hits = ret.search(query, top_k=top_k, kind=kind or None)
        return {"hits": [{"score": round(h.score, 3), "kind": h.kind,
                          "source": h.source, "text": h.text[:160]} for h in hits]}

    reg.register(Tool(
        name="rag_search",
        description="检索企业知识库(产品/资质/业绩/招标文本)。用于查历史业绩、产品资料等。",
        parameters={"type": "object",
                    "properties": {"query": {"type": "string", "description": "检索问句"},
                                   "kind": {"type": "string",
                                            "enum": ["", "product", "qualification",
                                                     "track_record", "tender"],
                                            "description": "类型过滤,可空"},
                                   "top_k": {"type": "integer", "description": "返回条数,默认5"}},
                    "required": ["query"]},
        handler=_rag_search,
    ))

    # ---- 写:导出报价 Word(确认门拦截) ----
    def _export_quote_docx(spec: str, quantity: int = 1, customer_tier: str = "C",
                           customer: str = "") -> dict:
        import tempfile
        from ..engines import Quotation
        oc = qa.quote_text(spec, quantity=quantity, customer_tier=customer_tier)
        if oc.quote is None:
            return {"error": oc.error or "报价失败"}
        q = Quotation(customer=customer, customer_tier=customer_tier, lines=[oc.quote])
        out = tempfile.mkstemp(suffix=".docx", prefix="quote_")[1]
        path = qa.export_quotation_docx(q, out)
        return {"path": str(path), "product_code": oc.quote.product_code,
                "line_total": oc.quote.line_total}

    reg.register(Tool(
        name="export_quote_docx",
        description="把报价导出为 Word 文件。⚠️写操作,需用户确认后执行。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP,
                                   "quantity": {"type": "integer"},
                                   "customer_tier": {"type": "string", "enum": ["A", "B", "C"]},
                                   "customer": {"type": "string", "description": "客户名称"}},
                    "required": ["spec"]},
        handler=_export_quote_docx,
        is_write=True,
    ))

    # ---- 写:报价同步 CRM(确认门拦截) ----
    def _sync_crm(spec: str, customer: str = "") -> dict:
        from ..engines import Quotation
        oc = qa.quote_text(spec, quantity=1, customer_tier="B")
        if oc.quote is None:
            return {"error": oc.error or "报价失败"}
        q = Quotation(customer=customer, lines=[oc.quote])
        res = qa.sync_to_crm(q, sync_dir=sync_dir, customer=customer)
        return {"external_id": res.external_id, "payload_path": str(res.payload_path)}

    reg.register(Tool(
        name="sync_crm",
        description="把报价回填 CRM 系统(文件适配器)。⚠️写外部系统,需用户确认后执行。",
        parameters={"type": "object",
                    "properties": {**_SPEC_PROP,
                                   "customer": {"type": "string", "description": "客户名称"}},
                    "required": ["spec"]},
        handler=_sync_crm,
        is_write=True,
    ))

    return reg
