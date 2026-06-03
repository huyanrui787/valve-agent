"""知识底座:价格版本化与材质规则测试。"""

from __future__ import annotations

from datetime import date

from valve_agent.models.enums import Medium


def test_price_versioning_picks_latest_before_basis(kb):
    # WCB 有 2025-01-01(12.0)、2026-01-01(13.5)、2026-05-01(14.2)
    assert kb.price_on("WCB", date(2025, 6, 1)).unit_price == 12.0
    assert kb.price_on("WCB", date(2026, 1, 1)).unit_price == 13.5
    assert kb.price_on("WCB", date(2026, 6, 4)).unit_price == 14.2


def test_price_before_any_effective_date_returns_none(kb):
    assert kb.price_on("WCB", date(2020, 1, 1)) is None


def test_unknown_material_price_is_none(kb):
    assert kb.price_on("NO_SUCH_MAT", date(2026, 6, 4)) is None


def test_steam_high_temp_forbids_soft_seal(kb):
    body, trim, notes = kb.allowed_materials(Medium.STEAM, 300, 100)
    # 高温蒸汽允许不锈钢/合金,不允许 PTFE 软密封
    assert "SS316" in body
    assert "PTFE" not in trim
    assert notes  # 命中规则有说明


def test_acid_requires_316(kb):
    body, trim, _ = kb.allowed_materials(Medium.ACID, 80, 40)
    assert body == {"SS316"}
    assert trim == {"SS316"}


def test_seed_counts(kb):
    assert len(kb.products) == 7
    assert len(kb.material_rules) == 6
    assert len(kb.qualifications) == 4
    assert len(kb.track_records) == 3
