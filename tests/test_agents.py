"""NL 解析 + 两个 Agent 端到端测试。"""

from __future__ import annotations

from datetime import date

from valve_agent.agents import BidAgent, QuoteAgent, QuoteRequestLine
from valve_agent.llm import ConditionParser
from valve_agent.models import CompareOp, TenderRequirement
from valve_agent.models.enums import DriveType, Medium, PressureUnit, ValveType


def test_parser_extracts_full_condition():
    c = ConditionParser().parse("球阀 DN200 PN40 蒸汽 250℃ 电动 API 316")
    assert c.dn == 200
    assert c.pressure_value == 40
    assert c.pressure_unit is PressureUnit.PN
    assert c.medium is Medium.STEAM
    assert c.temp_c == 250
    assert c.valve_type is ValveType.BALL
    assert c.drive is DriveType.ELECTRIC
    assert c.body_material_pref == "SS316"


def test_parser_class_pressure():
    c = ConditionParser().parse("闸阀 DN100 Class300 油品 200度")
    assert c.pressure_unit is PressureUnit.CLASS
    assert c.pressure_value == 300


def test_parser_missing_dn_raises():
    import pytest
    with pytest.raises(ValueError):
        ConditionParser().parse("球阀 PN40 蒸汽")


def test_quote_agent_text_to_quote(kb, basis):
    agent = QuoteAgent(kb)
    oc = agent.quote_text("球阀 DN200 PN40 蒸汽 250℃ 电动 API 316",
                          quantity=10, customer_tier="A", price_basis=basis)
    assert oc.error is None
    assert oc.quote.product_code == "Q41F-40P"
    assert oc.quote.line_total > 0
    assert oc.history_hint  # 有历史报价参考


def test_quote_agent_batch(kb, basis):
    agent = QuoteAgent(kb)
    lines = [
        QuoteRequestLine(text="球阀 DN200 PN40 蒸汽 250℃ 电动 316", quantity=5),
        QuoteRequestLine(text="蝶阀 DN300 PN16 水 80℃ 电动", quantity=20),
        QuoteRequestLine(text="无效行没有口径", quantity=1),
    ]
    quote, outcomes = agent.quote_batch(lines, customer="某水务", price_basis=basis)
    assert len(outcomes) == 3
    # 前两行成功,第三行报错
    assert outcomes[0].quote is not None
    assert outcomes[1].quote is not None
    assert outcomes[2].error is not None
    # 整单合计 = 成功两行之和
    assert quote.total > 0
    assert len(quote.lines) == 2


def test_bid_agent_package_closes_loop(kb, basis):
    qa = QuoteAgent(kb)
    ba = BidAgent(kb)
    oc = qa.quote_text("闸阀 DN200 PN100 蒸汽 350℃ 电动 API 316", price_basis=basis)
    best = oc.selection.best
    reqs = [
        TenderRequirement(param="公称压力", op=CompareOp.GE, target_value=40,
                          unit="bar", is_critical=True),
        TenderRequirement(param="工作温度", op=CompareOp.GE, target_value=300,
                          unit="℃", is_critical=True),
        TenderRequirement(param="执行标准", op=CompareOp.IN, target_set=["API"],
                          is_critical=True),
    ]
    pkg = ba.build_package(best.product, reqs, bid_date=basis,
                           chosen_body=best.chosen_body_material,
                           required_qual_categories=["ISO9001", "API6D"],
                           industry="电力")
    # 高等级闸阀:关键项无负偏离
    assert len(pkg.deviation_table.critical_negatives) == 0
    # 资质匹配到 ISO9001/API6D
    assert pkg.matched_qualifications["ISO9001"] is not None
    # 技术方案初稿非空(离线 stub)
    assert pkg.tech_proposal


def test_bid_agent_fills_negative_suggestion(kb, basis):
    qa = QuoteAgent(kb)
    ba = BidAgent(kb)
    oc = qa.quote_text("球阀 DN200 PN40 蒸汽 250℃ 电动 316", price_basis=basis)
    best = oc.selection.best
    reqs = [TenderRequirement(param="工作温度", op=CompareOp.GE, target_value=300,
                              unit="℃", is_critical=True)]
    pkg = ba.build_package(best.product, reqs, bid_date=basis,
                           chosen_body=best.chosen_body_material)
    neg = pkg.deviation_table.items[0]
    assert neg.verdict.value == "负偏离"
    assert neg.suggestion  # 话术已填充
