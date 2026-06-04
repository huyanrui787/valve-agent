"""智能标书 Agent(产品一的编排层)。

把"偏离表引擎 + 废标自检 + 资质业绩匹配 + 技术方案撰写"串成端到端能力。
与报价 Agent 联动:报价确定的型号可直接传入生成应答表(一次确定、两处复用)。

体现方案"AI 出 80% 初稿 + 专家 20% 把关":所有产物供人工复核。
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from ..engines import (
    BidComplianceEngine,
    ComplianceReport,
    DeviationTable,
    QualificationMatcher,
    WasteBidChecker,
)
from ..documents import TenderDocumentParser, export_bid_docx, load_document
from ..knowledge import KnowledgeBase
from ..llm import LLMProvider, get_provider
from ..models import Product, Qualification, TenderRequirement, TrackRecord
from ..models.tender import ParsedTender
from ..rag import RagRetriever


class BidPackage(BaseModel):
    """投标应答包 —— 标书 Agent 的端到端产物。"""

    product_code: str
    product_name: str
    deviation_table: DeviationTable
    compliance_report: ComplianceReport
    matched_qualifications: dict[str, Qualification | None] = Field(default_factory=dict)
    matched_records: list[TrackRecord] = Field(default_factory=list)
    tech_proposal: str = ""

    @property
    def can_bid(self) -> bool:
        """无高风险废标项即可投标(警告项需人工处理但不直接废标)。"""
        return not self.compliance_report.fails


class BidAgent:
    """智能标书 Agent。"""

    def __init__(
        self,
        kb: KnowledgeBase,
        llm: LLMProvider | None = None,
        retriever: RagRetriever | None = None,
    ) -> None:
        self.kb = kb
        self.compliance = BidComplianceEngine()
        self.checker = WasteBidChecker(kb)
        self.matcher = QualificationMatcher(kb)
        self.llm = llm or get_provider()
        self.retriever = retriever or RagRetriever(kb)
        self.tender_parser = TenderDocumentParser()

    def parse_tender_file(self, path: str) -> ParsedTender:
        """加载并解析招标文件(PDF/Word/文本)。"""
        text = load_document(path)
        return self.tender_parser.parse(text, source=str(path))

    def build_package(
        self,
        product: Product,
        requirements: list[TenderRequirement],
        bid_date: date | None = None,
        chosen_body: str | None = None,
        required_qual_categories: list[str] | None = None,
        min_track_records: int = 0,
        industry: str | None = None,
        write_proposal: bool = True,
    ) -> BidPackage:
        bid_date = bid_date or date.today()

        # 1. 技术偏离表(确定性判定 + 证据链)
        dt = self.compliance.assess(product, requirements, chosen_body)

        # 2. 负偏离话术由 LLM 表达层补充(离线 stub 给模板)
        for item in dt.items:
            if item.verdict.value == "负偏离" and not item.suggestion.strip():
                item.suggestion = self.llm.complete(
                    f"为以下技术偏离生成应答话术:{item.param} {item.requirement}",
                    system="你是阀门投标工程师")

        # 3. 资质业绩匹配
        matched_quals = (
            self.matcher.match_qualifications(required_qual_categories, bid_date)
            if required_qual_categories else {})
        matched_records = self.matcher.match_records(
            industry=industry, valve_type=product.valve_type.value, on=bid_date)

        # 4. 废标自检
        report = self.checker.check(
            bid_date=bid_date, deviation_tables=[dt],
            required_qual_categories=required_qual_categories,
            min_track_records=min_track_records, industry=industry)

        # 5. 技术方案初稿(RAG 上下文 + LLM 表达层)
        proposal = ""
        if write_proposal:
            ctx = self.retriever.context_for_proposal(
                product.code, f"{product.name} {product.valve_type.value}")
            prompt = f"为型号 {product.code}({product.name})撰写技术方案概述"
            if ctx:
                prompt += f"\n\n参考知识:\n{ctx}"
            proposal = self.llm.complete(prompt, system="你是阀门技术方案工程师")

        return BidPackage(
            product_code=product.code, product_name=product.name,
            deviation_table=dt, compliance_report=report,
            matched_qualifications=matched_quals, matched_records=matched_records,
            tech_proposal=proposal)

    def build_from_tender(
        self,
        tender: ParsedTender,
        product: Product,
        bid_date: date | None = None,
        chosen_body: str | None = None,
        write_proposal: bool = True,
    ) -> BidPackage:
        """用解析出的招标要求生成应答包(RAG 已索引招标文本)。"""
        self.retriever.ensure_indexed(tender)
        brief = tender.brief
        reqs = tender.requirements or []
        return self.build_package(
            product, reqs, bid_date=bid_date or brief.bid_deadline,
            chosen_body=chosen_body,
            required_qual_categories=brief.required_qual_categories or None,
            min_track_records=brief.min_track_records,
            industry=brief.industry_hint or None,
            write_proposal=write_proposal,
        )

    def export_docx(
        self,
        package: BidPackage,
        path: str,
        *,
        tender: ParsedTender | None = None,
        customer: str = "",
    ):
        """导出 Word 投标初稿。"""
        return export_bid_docx(package, path, tender=tender, customer=customer)
