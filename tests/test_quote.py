"""报价成本引擎测试。"""

from __future__ import annotations

from datetime import date

import pytest

from valve_agent.engines import QuoteEngine


def _product(kb, code):
    return kb.products[code]


def test_cost_breakdown_and_margin(kb, basis):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    ql = qe.quote_line(p, dn=200, body_material="SS316", trim_material="SS316",
                       quantity=1, customer_tier="C", price_basis=basis,
                       target_margin=0.30)
    # 成本拆解非空,单台成本 = 材料 + 加工 + 间接费
    assert ql.cost_lines
    expected = ql.material_cost + ql.processing_cost + ql.overhead
    assert ql.unit_cost == pytest.approx(expected, rel=1e-6)
    # 无折扣(C 级=1.0, 数量1=1.0)时实际毛利率≈目标 30%
    assert ql.margin == pytest.approx(0.30, abs=1e-3)
    # 含税单价 = 税前 × 1.13(单价已四舍五入到分,放宽容差)
    assert ql.unit_price == pytest.approx(ql.pre_tax_unit_price * 1.13, abs=0.01)


def test_volume_and_tier_discount_reduce_margin(kb, basis):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    base = qe.quote_line(p, 200, "SS316", "SS316", quantity=1, customer_tier="C",
                         price_basis=basis, target_margin=0.30)
    disc = qe.quote_line(p, 200, "SS316", "SS316", quantity=100, customer_tier="A",
                         price_basis=basis, target_margin=0.30)
    # 折扣后单价更低,毛利被压缩
    assert disc.pre_tax_unit_price < base.pre_tax_unit_price
    assert disc.margin < base.margin


def test_price_basis_affects_cost(kb):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-16C")  # 阀体 WCB
    old = qe.quote_line(p, 100, "WCB", "SS304", price_basis=date(2025, 6, 1))
    new = qe.quote_line(p, 100, "WCB", "SS304", price_basis=date(2026, 6, 4))
    # 2026 材料涨价 → 成本更高
    assert new.unit_cost > old.unit_cost


def test_larger_dn_costs_more(kb, basis):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    small = qe.quote_line(p, 50, "SS316", "SS316", price_basis=basis)
    large = qe.quote_line(p, 250, "SS316", "SS316", price_basis=basis)
    assert large.unit_cost > small.unit_cost


def test_invalid_margin_raises(kb, basis):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    with pytest.raises(ValueError):
        qe.quote_line(p, 200, "SS316", "SS316", price_basis=basis, target_margin=1.5)


def test_export_price_computed(kb, basis):
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    ql = qe.quote_line(p, 200, "SS316", "SS316", is_export=True, price_basis=basis)
    assert ql.export_unit_price_cny > 0


def test_stale_price_warning(kb):
    # 用远期基准日,使所有材料价格"过期" > 180 天
    qe = QuoteEngine(kb)
    p = _product(kb, "Q41F-40P")
    ql = qe.quote_line(p, 200, "SS316", "SS316", price_basis=date(2027, 6, 1))
    assert any("未更新" in w for w in ql.warnings)
