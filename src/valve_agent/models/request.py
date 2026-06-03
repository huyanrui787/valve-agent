"""请求/规格输入模型。

WorkingCondition —— 工况规格(选型与报价的统一输入)
TenderRequirement —— 招标技术要求的一条(参数名+比较符+目标值)
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .enums import (
    ConnectionType,
    DriveType,
    Medium,
    PressureUnit,
    Standard,
    ValveType,
    to_pn_bar,
)


class WorkingCondition(BaseModel):
    """工况规格 —— 选型引擎与报价引擎的统一输入。

    对应方案 4.1 "DN200、PN40、316、电动、蒸汽、API 600" 这类描述。
    """

    dn: int = Field(description="公称通径 mm")
    pressure_value: float = Field(description="压力等级数值")
    pressure_unit: PressureUnit = PressureUnit.PN
    medium: Medium
    temp_c: float = Field(description="工作温度 ℃")
    valve_type: ValveType | None = None
    drive: DriveType | None = None
    connection: ConnectionType | None = None
    standard: Standard | None = None
    body_material_pref: str | None = Field(
        None, description="阀体材质偏好,如 316/304/WCB"
    )

    @property
    def pn_bar(self) -> float:
        """统一换算成 PN(bar)口径。"""
        return to_pn_bar(self.pressure_value, self.pressure_unit)


class CompareOp(str, Enum):
    """招标参数的比较符。"""

    GE = ">="
    LE = "<="
    EQ = "=="
    GT = ">"
    LT = "<"
    IN = "in"  # 目标值为枚举集合,要求产品能力命中


class TenderRequirement(BaseModel):
    """招标技术要求的一条。

    例:参数名=公称压力, op=>=, target=40 (单位 bar) → 要求产品 PN 至少 40。
    higher_is_better 决定"超出要求"算正偏离还是负偏离。
    """

    param: str = Field(description="参数名,如 公称压力/公称通径/工作温度/阀体材质/执行标准")
    op: CompareOp
    target_value: float | None = None
    target_text: str | None = Field(None, description="文本/枚举类目标值")
    target_set: list[str] | None = Field(None, description="op=in 时的可选集合")
    unit: str = ""
    higher_is_better: bool = Field(
        True, description="参数值越大越好(如压力/温度上限)则 True"
    )
    is_critical: bool = Field(False, description="是否关键项(负偏离可能废标)")
    raw: str = Field("", description="原始招标条款文本")
