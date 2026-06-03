"""自然语言工况解析(对应方案 4.1 自然语言/参数化选型)。

规则化解析:从 "DN200、PN40、316、电动、蒸汽、API 600" 这类描述抽取结构化工况。
确定性优先(正则 + 关键词),LLM 可在此之上做兜底/纠错。
"""

from __future__ import annotations

import re

from ..models import WorkingCondition
from ..models.enums import (
    ConnectionType,
    DriveType,
    Medium,
    PressureUnit,
    Standard,
    ValveType,
)

_VALVE_KW = {
    "球阀": ValveType.BALL, "ball": ValveType.BALL,
    "闸阀": ValveType.GATE, "gate": ValveType.GATE,
    "截止阀": ValveType.GLOBE, "globe": ValveType.GLOBE,
    "蝶阀": ValveType.BUTTERFLY, "butterfly": ValveType.BUTTERFLY,
    "止回阀": ValveType.CHECK, "check": ValveType.CHECK,
}
_DRIVE_KW = {
    "电动": DriveType.ELECTRIC, "气动": DriveType.PNEUMATIC,
    "液动": DriveType.HYDRAULIC, "手动": DriveType.MANUAL,
}
_CONN_KW = {
    "法兰": ConnectionType.FLANGE, "对焊": ConnectionType.WELD,
    "焊接": ConnectionType.WELD, "螺纹": ConnectionType.THREAD,
}
_MEDIUM_KW = {
    "蒸汽": Medium.STEAM, "水": Medium.WATER, "油": Medium.OIL,
    "天然气": Medium.GAS, "燃气": Medium.GAS, "酸": Medium.ACID,
    "压缩空气": Medium.AIR, "空气": Medium.AIR,
}
_STD_KW = {
    "api": Standard.API, "ansi": Standard.ANSI, "asme": Standard.ANSI,
    "iso": Standard.ISO, "gb": Standard.GB, "国标": Standard.GB,
}
_MATERIAL_KW = ["316L", "316", "304", "WCB", "WC6", "QT450", "Stellite"]


class ConditionParser:
    """工况文本解析器。"""

    def parse(self, text: str) -> WorkingCondition:
        raw = text
        low = text.lower()

        dn = self._first_int(re.search(r"dn\s*(\d+)", low))
        if dn is None:
            raise ValueError(f"无法解析公称通径(DN):{raw!r}")

        # 压力:优先 Class,其次 PN
        pressure_value: float
        pressure_unit: PressureUnit
        m_class = re.search(r"class\s*(\d+)", low)
        m_pn = re.search(r"pn\s*(\d+(?:\.\d+)?)", low)
        if m_class:
            pressure_value = float(m_class.group(1))
            pressure_unit = PressureUnit.CLASS
        elif m_pn:
            pressure_value = float(m_pn.group(1))
            pressure_unit = PressureUnit.PN
        else:
            raise ValueError(f"无法解析压力等级(PN/Class):{raw!r}")

        # 温度
        temp_c = 20.0
        m_temp = re.search(r"(-?\d+(?:\.\d+)?)\s*(?:℃|°c|度|c\b)", low)
        if m_temp:
            temp_c = float(m_temp.group(1))

        medium = self._match_kw(text, _MEDIUM_KW) or Medium.WATER
        valve_type = self._match_kw(text, _VALVE_KW)
        drive = self._match_kw(text, _DRIVE_KW)
        connection = self._match_kw(text, _CONN_KW)
        standard = self._match_kw(low, _STD_KW)

        body_pref = None
        for mk in _MATERIAL_KW:
            if mk.lower() in low:
                body_pref = "SS316" if mk in ("316", "316L") else (
                    "SS304" if mk == "304" else mk)
                break

        return WorkingCondition(
            dn=dn,
            pressure_value=pressure_value,
            pressure_unit=pressure_unit,
            medium=medium,
            temp_c=temp_c,
            valve_type=valve_type,
            drive=drive,
            connection=connection,
            standard=standard,
            body_material_pref=body_pref,
        )

    @staticmethod
    def _first_int(m: re.Match | None) -> int | None:
        return int(m.group(1)) if m else None

    @staticmethod
    def _match_kw(text: str, table: dict):
        for kw, val in table.items():
            if kw in text:
                return val
        return None
