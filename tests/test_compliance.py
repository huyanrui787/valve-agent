"""标书偏离表 + 废标自检测试。"""

from __future__ import annotations

from datetime import date

from valve_agent.engines import BidComplianceEngine, Verdict, WasteBidChecker
from valve_agent.engines.waste_bid import RiskLevel
from valve_agent.models import CompareOp, TenderRequirement


def _reqs():
    return [
        TenderRequirement(param="公称压力", op=CompareOp.GE, target_value=40,
                          unit="bar", is_critical=True),
        TenderRequirement(param="公称通径", op=CompareOp.GE, target_value=100,
                          unit="mm"),
        TenderRequirement(param="工作温度", op=CompareOp.GE, target_value=300,
                          unit="℃", is_critical=True),
        TenderRequirement(param="执行标准", op=CompareOp.IN, target_set=["API"],
                          is_critical=True),
    ]


def test_satisfy_positive_negative_verdicts(kb):
    p = kb.products["Q41F-40P"]  # PN25-40, -40~250℃
    dt = BidComplianceEngine().assess(p, _reqs(), chosen_body="SS316")
    by_param = {i.param: i for i in dt.items}
    # PN 要求 >=40,产品上限正好 40 → 满足
    assert by_param["公称压力"].verdict is Verdict.SATISFY
    # DN 要求 >=100,产品上限 250 > 100 → 正偏离
    assert by_param["公称通径"].verdict is Verdict.POSITIVE
    # 温度要求 >=300,产品上限 250 → 负偏离(关键)
    assert by_param["工作温度"].verdict is Verdict.NEGATIVE
    assert by_param["工作温度"].is_critical


def test_deviation_items_have_evidence(kb):
    p = kb.products["Q41F-40P"]
    dt = BidComplianceEngine().assess(p, _reqs(), chosen_body="SS316")
    for i in dt.items:
        assert i.evidence  # 每条都有证据链


def test_negative_item_has_suggestion(kb):
    p = kb.products["Q41F-40P"]
    dt = BidComplianceEngine().assess(p, _reqs(), chosen_body="SS316")
    neg = next(i for i in dt.items if i.verdict is Verdict.NEGATIVE)
    assert neg.suggestion


def test_higher_grade_valve_clears_critical(kb):
    p = kb.products["Z41H-100P"]  # PN63-100, -40~425℃, API
    dt = BidComplianceEngine().assess(p, _reqs(), chosen_body="SS316")
    assert dt.negative_count == 0
    assert len(dt.critical_negatives) == 0


def test_unknown_param_is_unknown(kb):
    p = kb.products["Q41F-40P"]
    reqs = [TenderRequirement(param="噪声等级", op=CompareOp.LE, target_value=85)]
    dt = BidComplianceEngine().assess(p, reqs)
    assert dt.items[0].verdict is Verdict.UNKNOWN


def test_waste_bid_critical_negative_fails(kb, basis):
    p = kb.products["Q41F-40P"]
    dt = BidComplianceEngine().assess(p, _reqs(), chosen_body="SS316")
    report = WasteBidChecker(kb).check(bid_date=basis, deviation_tables=[dt])
    assert report.overall is RiskLevel.FAIL
    assert any("关键技术响应" in i.name for i in report.fails)


def test_waste_bid_track_record_shortfall(kb, basis):
    report = WasteBidChecker(kb).check(
        bid_date=basis, min_track_records=3, industry="电力")
    # 电力业绩只有 1 项 < 3 → 高风险
    assert any("业绩数量" in i.name and i.level is RiskLevel.FAIL
               for i in report.items)


def test_expired_qualification_fails(kb):
    # 特种设备许可证 2026-08-01 到期;投标日设在之后 → 过期高风险
    report = WasteBidChecker(kb).check(bid_date=date(2026, 12, 1))
    assert any("特种设备" in i.name and i.level is RiskLevel.FAIL
               for i in report.items)


def test_qualification_expiry_warning(kb, basis):
    # 投标日 2026-06-04,许可证 2026-08-01 到期(<90天)→ 预警
    report = WasteBidChecker(kb).check(bid_date=basis)
    assert any("特种设备" in i.name and i.level is RiskLevel.WARN
               for i in report.items)
