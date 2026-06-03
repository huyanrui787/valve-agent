"""阀门种子数据 —— 构建一个可演示的知识底座。

涵盖球阀/闸阀/截止阀/蝶阀/止回阀若干典型型号、材质规则、版本化材料价格、
资质证照与历史业绩。用于离线 demo 与测试,数据为合理示意值,非真实报价。
"""

from __future__ import annotations

from datetime import date

from ..models import (
    BomLine,
    BomTemplate,
    DNRange,
    MaterialPrice,
    MaterialRule,
    PNRange,
    Product,
    Qualification,
    TempRange,
    TrackRecord,
)
from ..models.enums import (
    ConnectionType,
    DriveType,
    Medium,
    Standard,
    ValveType,
)
from .repository import KnowledgeBase


def _bom_ball() -> BomTemplate:
    """球阀 BOM 模板。qty_per_dn 体现随口径放大的算量。"""
    return BomTemplate(
        id="BOM-BALL",
        description="球阀通用 BOM",
        lines=[
            BomLine(name="阀体毛坯", material_key="WCB", qty_base=2.0, qty_per_dn=0.12, unit="kg"),
            BomLine(name="球体", material_key="SS304", qty_base=0.5, qty_per_dn=0.05, unit="kg"),
            BomLine(name="阀座", material_key="PTFE", qty_base=0.1, qty_per_dn=0.008, unit="kg"),
            BomLine(name="阀杆", material_key="SS316", qty_base=0.3, qty_per_dn=0.01, unit="kg"),
            BomLine(name="密封件", material_key="PTFE", qty_base=0.05, qty_per_dn=0.003, unit="kg"),
            BomLine(name="紧固件", material_key="SS304", qty_base=0.2, qty_per_dn=0.006, unit="kg"),
            BomLine(name="机加工费", qty_base=1, fixed_cost=180.0),
            BomLine(name="试验检测费", qty_base=1, fixed_cost=120.0),
            BomLine(name="表面处理", qty_base=1, fixed_cost=60.0),
            BomLine(name="包装运输", qty_base=1, fixed_cost=50.0),
        ],
    )


def _bom_gate() -> BomTemplate:
    return BomTemplate(
        id="BOM-GATE",
        description="闸阀通用 BOM",
        lines=[
            BomLine(name="阀体毛坯", material_key="WCB", qty_base=3.0, qty_per_dn=0.18, unit="kg"),
            BomLine(name="闸板", material_key="SS304", qty_base=0.8, qty_per_dn=0.06, unit="kg"),
            BomLine(name="阀座", material_key="SS316", qty_base=0.2, qty_per_dn=0.01, unit="kg"),
            BomLine(name="阀杆", material_key="SS316", qty_base=0.5, qty_per_dn=0.015, unit="kg"),
            BomLine(name="密封填料", material_key="GRAPHITE", qty_base=0.1, qty_per_dn=0.004, unit="kg"),
            BomLine(name="紧固件", material_key="SS304", qty_base=0.3, qty_per_dn=0.008, unit="kg"),
            BomLine(name="机加工费", qty_base=1, fixed_cost=260.0),
            BomLine(name="试验检测费", qty_base=1, fixed_cost=160.0),
            BomLine(name="表面处理", qty_base=1, fixed_cost=80.0),
            BomLine(name="包装运输", qty_base=1, fixed_cost=70.0),
        ],
    )


def _bom_globe() -> BomTemplate:
    return BomTemplate(
        id="BOM-GLOBE",
        description="截止阀通用 BOM",
        lines=[
            BomLine(name="阀体毛坯", material_key="WCB", qty_base=2.5, qty_per_dn=0.15, unit="kg"),
            BomLine(name="阀瓣", material_key="SS316", qty_base=0.6, qty_per_dn=0.04, unit="kg"),
            BomLine(name="阀座", material_key="SS316", qty_base=0.2, qty_per_dn=0.01, unit="kg"),
            BomLine(name="阀杆", material_key="SS316", qty_base=0.4, qty_per_dn=0.012, unit="kg"),
            BomLine(name="密封填料", material_key="GRAPHITE", qty_base=0.08, qty_per_dn=0.003, unit="kg"),
            BomLine(name="机加工费", qty_base=1, fixed_cost=220.0),
            BomLine(name="试验检测费", qty_base=1, fixed_cost=150.0),
            BomLine(name="表面处理", qty_base=1, fixed_cost=70.0),
            BomLine(name="包装运输", qty_base=1, fixed_cost=60.0),
        ],
    )


def _bom_butterfly() -> BomTemplate:
    return BomTemplate(
        id="BOM-BFLY",
        description="蝶阀通用 BOM",
        lines=[
            BomLine(name="阀体", material_key="WCB", qty_base=1.5, qty_per_dn=0.10, unit="kg"),
            BomLine(name="蝶板", material_key="SS304", qty_base=0.4, qty_per_dn=0.05, unit="kg"),
            BomLine(name="阀座", material_key="EPDM", qty_base=0.1, qty_per_dn=0.006, unit="kg"),
            BomLine(name="阀杆", material_key="SS316", qty_base=0.3, qty_per_dn=0.01, unit="kg"),
            BomLine(name="机加工费", qty_base=1, fixed_cost=140.0),
            BomLine(name="试验检测费", qty_base=1, fixed_cost=90.0),
            BomLine(name="包装运输", qty_base=1, fixed_cost=45.0),
        ],
    )


def _bom_check() -> BomTemplate:
    return BomTemplate(
        id="BOM-CHECK",
        description="止回阀通用 BOM",
        lines=[
            BomLine(name="阀体", material_key="WCB", qty_base=2.0, qty_per_dn=0.13, unit="kg"),
            BomLine(name="阀瓣", material_key="SS304", qty_base=0.5, qty_per_dn=0.04, unit="kg"),
            BomLine(name="阀座", material_key="SS316", qty_base=0.15, qty_per_dn=0.008, unit="kg"),
            BomLine(name="弹簧/销轴", material_key="SS316", qty_base=0.2, qty_per_dn=0.005, unit="kg"),
            BomLine(name="机加工费", qty_base=1, fixed_cost=160.0),
            BomLine(name="试验检测费", qty_base=1, fixed_cost=110.0),
            BomLine(name="包装运输", qty_base=1, fixed_cost=50.0),
        ],
    )


def build_demo_kb(basis: date | None = None) -> KnowledgeBase:
    """构建一个填充好的演示知识底座。"""
    kb = KnowledgeBase()

    # ---- BOM 模板 ----
    for b in (_bom_ball(), _bom_gate(), _bom_globe(), _bom_butterfly(), _bom_check()):
        kb.add_bom(b)

    # ---- 产品型号 ----
    products = [
        Product(
            code="Q41F-16C",
            name="碳钢法兰球阀 PN16",
            valve_type=ValveType.BALL,
            dn_range=DNRange(min_dn=15, max_dn=300),
            pn_range=PNRange(min_pn=10, max_pn=16),
            temp_range=TempRange(min_c=-20, max_c=180),
            body_materials=["WCB"],
            trim_materials=["SS304", "SS316"],
            seal_types=["PTFE 软密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC, DriveType.PNEUMATIC],
            connections=[ConnectionType.FLANGE],
            media=[Medium.WATER, Medium.OIL, Medium.AIR, Medium.GAS],
            standards=[Standard.GB, Standard.API],
            bom_template_id="BOM-BALL",
        ),
        Product(
            code="Q41F-40P",
            name="不锈钢法兰球阀 PN40",
            valve_type=ValveType.BALL,
            dn_range=DNRange(min_dn=15, max_dn=250),
            pn_range=PNRange(min_pn=25, max_pn=40),
            temp_range=TempRange(min_c=-40, max_c=250),
            body_materials=["SS304", "SS316"],
            trim_materials=["SS316"],
            seal_types=["PTFE 软密封", "金属硬密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC, DriveType.PNEUMATIC],
            connections=[ConnectionType.FLANGE, ConnectionType.WELD],
            media=[Medium.WATER, Medium.OIL, Medium.GAS, Medium.STEAM, Medium.ACID],
            standards=[Standard.GB, Standard.API, Standard.ANSI],
            bom_template_id="BOM-BALL",
        ),
        Product(
            code="Z41H-16C",
            name="碳钢法兰闸阀 PN16",
            valve_type=ValveType.GATE,
            dn_range=DNRange(min_dn=50, max_dn=600),
            pn_range=PNRange(min_pn=10, max_pn=16),
            temp_range=TempRange(min_c=-20, max_c=200),
            body_materials=["WCB"],
            trim_materials=["SS304"],
            seal_types=["楔式硬密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC],
            connections=[ConnectionType.FLANGE],
            media=[Medium.WATER, Medium.OIL, Medium.STEAM],
            standards=[Standard.GB],
            bom_template_id="BOM-GATE",
        ),
        Product(
            code="Z41H-100P",
            name="不锈钢法兰闸阀 PN100",
            valve_type=ValveType.GATE,
            dn_range=DNRange(min_dn=50, max_dn=400),
            pn_range=PNRange(min_pn=63, max_pn=100),
            temp_range=TempRange(min_c=-40, max_c=425),
            body_materials=["SS316", "WC6"],
            trim_materials=["SS316", "Stellite"],
            seal_types=["楔式硬密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC, DriveType.HYDRAULIC],
            connections=[ConnectionType.FLANGE, ConnectionType.WELD],
            media=[Medium.STEAM, Medium.OIL, Medium.GAS, Medium.WATER],
            standards=[Standard.API, Standard.ANSI],
            bom_template_id="BOM-GATE",
        ),
        Product(
            code="J41H-25",
            name="截止阀 PN25",
            valve_type=ValveType.GLOBE,
            dn_range=DNRange(min_dn=15, max_dn=250),
            pn_range=PNRange(min_pn=16, max_pn=25),
            temp_range=TempRange(min_c=-29, max_c=350),
            body_materials=["WCB", "SS316"],
            trim_materials=["SS316", "Stellite"],
            seal_types=["锥面硬密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC],
            connections=[ConnectionType.FLANGE, ConnectionType.WELD],
            media=[Medium.STEAM, Medium.WATER, Medium.OIL],
            standards=[Standard.GB, Standard.API],
            bom_template_id="BOM-GLOBE",
        ),
        Product(
            code="D371X-16",
            name="对夹蝶阀 PN16",
            valve_type=ValveType.BUTTERFLY,
            dn_range=DNRange(min_dn=50, max_dn=1200),
            pn_range=PNRange(min_pn=6, max_pn=16),
            temp_range=TempRange(min_c=-10, max_c=120),
            body_materials=["WCB", "QT450"],
            trim_materials=["SS304"],
            seal_types=["EPDM 软密封"],
            drives=[DriveType.MANUAL, DriveType.ELECTRIC, DriveType.PNEUMATIC],
            connections=[ConnectionType.FLANGE],
            media=[Medium.WATER, Medium.AIR],
            standards=[Standard.GB],
            bom_template_id="BOM-BFLY",
        ),
        Product(
            code="H41H-16C",
            name="升降式止回阀 PN16",
            valve_type=ValveType.CHECK,
            dn_range=DNRange(min_dn=15, max_dn=300),
            pn_range=PNRange(min_pn=10, max_pn=16),
            temp_range=TempRange(min_c=-20, max_c=200),
            body_materials=["WCB"],
            trim_materials=["SS304", "SS316"],
            seal_types=["金属密封"],
            drives=[DriveType.MANUAL],
            connections=[ConnectionType.FLANGE],
            media=[Medium.WATER, Medium.OIL, Medium.STEAM],
            standards=[Standard.GB, Standard.API],
            bom_template_id="BOM-CHECK",
        ),
    ]
    for p in products:
        kb.add_product(p)

    # ---- 材质规则:介质+温度+压力 → 允许材质 ----
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.STEAM,
            temp_range=TempRange(min_c=100, max_c=450),
            max_pn=420,
            allowed_body_materials=["SS316", "WC6", "WCB"],
            allowed_trim_materials=["SS316", "Stellite"],
            note="高温蒸汽:禁用 PTFE 等软密封,阀座需硬密封/Stellite",
        )
    )
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.ACID,
            temp_range=TempRange(min_c=-40, max_c=200),
            max_pn=100,
            allowed_body_materials=["SS316"],
            allowed_trim_materials=["SS316"],
            note="酸性介质:阀体阀芯须 316 以上耐蚀材质",
        )
    )
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.WATER,
            temp_range=TempRange(min_c=-20, max_c=120),
            max_pn=40,
            allowed_body_materials=["WCB", "SS304", "SS316", "QT450"],
            allowed_trim_materials=["SS304", "SS316"],
            note="常温水介质:碳钢/不锈钢均可",
        )
    )
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.OIL,
            temp_range=TempRange(min_c=-40, max_c=250),
            max_pn=100,
            allowed_body_materials=["WCB", "SS304", "SS316"],
            allowed_trim_materials=["SS304", "SS316", "Stellite"],
            note="油品介质:碳钢/不锈钢,高温段优选不锈钢",
        )
    )
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.GAS,
            temp_range=TempRange(min_c=-40, max_c=180),
            max_pn=100,
            allowed_body_materials=["WCB", "SS304", "SS316"],
            allowed_trim_materials=["SS304", "SS316"],
            note="天然气:防火安全型,软硬密封均可",
        )
    )
    kb.add_material_rule(
        MaterialRule(
            medium=Medium.AIR,
            temp_range=TempRange(min_c=-10, max_c=120),
            max_pn=40,
            allowed_body_materials=["WCB", "QT450", "SS304"],
            allowed_trim_materials=["SS304"],
            note="压缩空气:常规材质即可",
        )
    )

    # ---- 价格库(版本化:同一材料多个生效日期) ----
    prices = [
        # WCB 碳钢
        ("WCB", "WCB 碳钢", 12.0, date(2025, 1, 1)),
        ("WCB", "WCB 碳钢", 13.5, date(2026, 1, 1)),
        ("WCB", "WCB 碳钢", 14.2, date(2026, 5, 1)),
        # 304
        ("SS304", "304 不锈钢", 28.0, date(2025, 1, 1)),
        ("SS304", "304 不锈钢", 31.0, date(2026, 1, 1)),
        ("SS304", "304 不锈钢", 33.5, date(2026, 5, 1)),
        # 316
        ("SS316", "316 不锈钢", 42.0, date(2025, 1, 1)),
        ("SS316", "316 不锈钢", 46.0, date(2026, 1, 1)),
        ("SS316", "316 不锈钢", 49.0, date(2026, 5, 1)),
        # 合金钢 WC6
        ("WC6", "WC6 合金钢", 35.0, date(2026, 1, 1)),
        # 球墨铸铁
        ("QT450", "QT450 球墨铸铁", 9.5, date(2026, 1, 1)),
        # 司太立硬质合金堆焊
        ("Stellite", "Stellite 堆焊层", 180.0, date(2026, 1, 1)),
        # 软密封/填料
        ("PTFE", "PTFE 聚四氟乙烯", 65.0, date(2026, 1, 1)),
        ("GRAPHITE", "柔性石墨填料", 40.0, date(2026, 1, 1)),
        ("EPDM", "EPDM 橡胶", 22.0, date(2026, 1, 1)),
    ]
    for key, name, price, eff in prices:
        kb.add_price(
            MaterialPrice(
                material_key=key,
                name=name,
                unit_price=price,
                effective_date=eff,
                source="种子数据",
            )
        )

    # ---- 资质证照 ----
    kb.add_qualification(
        Qualification(
            name="ISO9001 质量管理体系认证",
            category="ISO9001",
            issuer="CQC",
            cert_no="ISO9001-2024-XXXX",
            valid_until=date(2027, 6, 30),
        )
    )
    kb.add_qualification(
        Qualification(
            name="API 6D 会员认证",
            category="API6D",
            issuer="API",
            cert_no="API-6D-XXXX",
            valid_until=date(2027, 3, 31),
        )
    )
    kb.add_qualification(
        Qualification(
            name="API 607 防火测试报告",
            category="API607",
            issuer="第三方实验室",
            cert_no="FIRE-2025-XX",
            valid_until=date(2028, 1, 1),
        )
    )
    kb.add_qualification(
        Qualification(
            name="特种设备制造许可证(压力管道阀门)",
            category="TS",
            issuer="国家市场监督管理总局",
            cert_no="TS-XXXX",
            valid_until=date(2026, 8, 1),  # 临近到期,演示废标自检预警
        )
    )

    # ---- 历史业绩 ----
    kb.add_track_record(
        TrackRecord(
            project_name="某石化常减压装置阀门供货",
            customer="中石化某炼化",
            industry="石化",
            valve_type="球阀/闸阀",
            contract_date=date(2024, 6, 1),
            amount=3_200_000,
            summary="DN50-300 PN40 不锈钢球阀、闸阀共 480 台",
        )
    )
    kb.add_track_record(
        TrackRecord(
            project_name="某电厂高温蒸汽管线阀门",
            customer="某发电集团",
            industry="电力",
            valve_type="闸阀/截止阀",
            contract_date=date(2025, 3, 15),
            amount=2_750_000,
            summary="DN100-400 PN100 高温闸阀、截止阀 260 台",
        )
    )
    kb.add_track_record(
        TrackRecord(
            project_name="市政供水管网阀门集采",
            customer="某市水务集团",
            industry="水务",
            valve_type="蝶阀/闸阀",
            contract_date=date(2025, 9, 1),
            amount=1_900_000,
            summary="DN200-1000 PN16 蝶阀、软密封闸阀 600 台",
        )
    )

    return kb
