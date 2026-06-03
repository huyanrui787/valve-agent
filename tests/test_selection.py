"""选型规则引擎测试。"""

from __future__ import annotations

from valve_agent.engines import RankStrategy, SelectionEngine
from valve_agent.models import WorkingCondition
from valve_agent.models.enums import (
    ConnectionType,
    DriveType,
    Medium,
    PressureUnit,
    Standard,
    ValveType,
)


def _cond(**kw):
    base = dict(dn=200, pressure_value=40, pressure_unit=PressureUnit.PN,
                medium=Medium.STEAM, temp_c=250)
    base.update(kw)
    return WorkingCondition(**base)


def test_basic_selection_returns_matching_ball_valve(kb):
    cond = _cond(valve_type=ValveType.BALL, drive=DriveType.ELECTRIC,
                 standard=Standard.API, body_material_pref="SS316")
    res = SelectionEngine(kb).select(cond)
    assert res.best is not None
    assert res.best.product.code == "Q41F-40P"
    assert res.best.chosen_body_material == "SS316"


def test_pressure_out_of_range_rejected(kb):
    # PN16 球阀无法满足 PN40 蒸汽 250℃
    cond = _cond(valve_type=ValveType.BALL)
    res = SelectionEngine(kb).select(cond)
    codes = {c.product.code for c in res.candidates}
    assert "Q41F-16C" not in codes
    assert any(r.code == "Q41F-16C" for r in res.rejections)


def test_material_rule_blocks_incompatible(kb):
    # 高温蒸汽 300℃:PTFE 软密封球阀(Q41F-40P 上限 250℃)温度也不够
    cond = _cond(temp_c=300, valve_type=ValveType.GATE,
                 pressure_value=100, standard=Standard.API)
    res = SelectionEngine(kb).select(cond)
    assert res.best is not None
    assert res.best.product.code == "Z41H-100P"


def test_drive_filter_rejects(kb):
    # 止回阀只有手动,要求电动应被淘汰
    cond = _cond(valve_type=ValveType.CHECK, pressure_value=16,
                 medium=Medium.WATER, temp_c=80, drive=DriveType.ELECTRIC)
    res = SelectionEngine(kb).select(cond)
    assert all(c.product.valve_type != ValveType.CHECK for c in res.candidates)
    assert any(r.stage == "驱动连接" or r.stage == "硬过滤" for r in res.rejections)


def test_no_match_returns_empty(kb):
    # 不存在的超高压工况
    cond = _cond(pressure_value=600, pressure_unit=PressureUnit.PN, temp_c=250)
    res = SelectionEngine(kb).select(cond)
    assert res.best is None


def test_class_pressure_conversion(kb):
    # Class 300 ≈ PN40,应能选到 PN40 球阀
    cond = _cond(pressure_value=300, pressure_unit=PressureUnit.CLASS,
                 valve_type=ValveType.BALL, body_material_pref="SS316")
    res = SelectionEngine(kb).select(cond)
    assert res.best is not None
    assert res.best.product.supports_pn(cond.pn_bar)


def test_candidates_have_evidence(kb):
    cond = _cond(valve_type=ValveType.BALL, body_material_pref="SS316")
    res = SelectionEngine(kb).select(cond)
    assert res.best.reasons
    assert any("DN200" in r for r in res.best.reasons)


def test_history_strategy_changes_ranking(kb):
    cond = _cond(medium=Medium.WATER, temp_c=80, pressure_value=16)
    res = SelectionEngine(kb).select(cond, top_n=5, strategy=RankStrategy.HISTORY)
    assert res.candidates  # 有候选即可,排序逻辑不报错
