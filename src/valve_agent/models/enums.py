"""阀门领域的枚举与基础值对象。

集中定义阀类、驱动方式、连接方式、介质、标准体系等枚举,
作为产品库、选型引擎、报价引擎共用的"领域词汇表"。
"""

from __future__ import annotations

from enum import Enum


class ValveType(str, Enum):
    """阀门类别。"""

    BALL = "球阀"
    GATE = "闸阀"
    GLOBE = "截止阀"
    BUTTERFLY = "蝶阀"
    CHECK = "止回阀"


class DriveType(str, Enum):
    """驱动方式。"""

    MANUAL = "手动"
    ELECTRIC = "电动"
    PNEUMATIC = "气动"
    HYDRAULIC = "液动"


class ConnectionType(str, Enum):
    """连接方式。"""

    FLANGE = "法兰"
    WELD = "对焊"
    THREAD = "螺纹"


class Medium(str, Enum):
    """适用介质。决定材质规则的关键变量之一。"""

    WATER = "水"
    OIL = "油品"
    GAS = "天然气"
    STEAM = "蒸汽"
    ACID = "酸性介质"
    AIR = "压缩空气"


class Standard(str, Enum):
    """执行标准体系。"""

    GB = "GB/T"
    API = "API"
    ANSI = "ANSI/ASME"
    ISO = "ISO"


class PressureUnit(str, Enum):
    """压力等级体系。PN(公称压力, bar)与 Class(磅级)。"""

    PN = "PN"
    CLASS = "Class"


# Class 磅级与 PN(bar)的近似换算,用于跨体系比较压力等级。
# 来源:常用工程对照表(ASME B16.34 / GB 对照)。
CLASS_TO_PN: dict[int, int] = {
    150: 16,
    300: 40,
    600: 100,
    900: 150,
    1500: 250,
    2500: 420,
}


def to_pn_bar(value: float, unit: PressureUnit) -> float:
    """把压力等级统一换算成 PN(bar)口径,便于跨体系比较。"""
    if unit is PressureUnit.PN:
        return float(value)
    # Class:按对照表换算,落在区间则线性近似,超表则用最接近端点。
    iv = int(value)
    if iv in CLASS_TO_PN:
        return float(CLASS_TO_PN[iv])
    keys = sorted(CLASS_TO_PN)
    if iv <= keys[0]:
        return float(CLASS_TO_PN[keys[0]])
    if iv >= keys[-1]:
        return float(CLASS_TO_PN[keys[-1]])
    # 线性插值
    lo = max(k for k in keys if k <= iv)
    hi = min(k for k in keys if k >= iv)
    if lo == hi:
        return float(CLASS_TO_PN[lo])
    frac = (iv - lo) / (hi - lo)
    return CLASS_TO_PN[lo] + frac * (CLASS_TO_PN[hi] - CLASS_TO_PN[lo])
