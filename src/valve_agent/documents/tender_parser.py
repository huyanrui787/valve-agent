"""招标文件规则解析器(确定性优先)。

从 PDF/Word 抽取的纯文本中识别:
  - 技术参数要求 → TenderRequirement
  - 废标条款摘录
  - 投标截止日、资质类别、业绩数量、行业等要点

LLM 可在上层对 brief 做润色;硬逻辑与偏离判定仍走规则引擎。
"""

from __future__ import annotations

import re
from datetime import date

from ..models import CompareOp, TenderRequirement
from ..models.tender import ParsedTender, RiskItem, TenderBrief

# 技术参数: (参数名, 正则, op, unit, is_critical)
_TECH_RULES: list[tuple[str, re.Pattern[str], CompareOp, str, bool]] = [
    (
        "公称压力",
        re.compile(
            r"公称压力[^。\n]{0,60}?(?:不低于|不少于|≥|>=|应达到)\s*(\d+(?:\.\d+)?)\s*(?:bar|BAR|Bar|MPa)?",
            re.I,
        ),
        CompareOp.GE,
        "bar",
        True,
    ),
    (
        "公称压力",
        re.compile(r"PN\s*(\d+(?:\.\d+)?)\s*(?:及以上|以上|不低于)", re.I),
        CompareOp.GE,
        "bar",
        True,
    ),
    (
        "公称通径",
        re.compile(
            r"公称通径[^。\n]{0,60}?(?:不低于|不少于|≥|>=)\s*(?:DN\s*)?(\d+)",
            re.I,
        ),
        CompareOp.GE,
        "mm",
        False,
    ),
    (
        "公称通径",
        re.compile(r"DN\s*(\d+)\s*(?:及以上|以上|不低于)", re.I),
        CompareOp.GE,
        "mm",
        False,
    ),
    (
        "工作温度",
        re.compile(
            r"(?:工作温度|设计温度|介质温度)[^。\n]{0,60}?(?:不低于|不少于|≥|>=|达到)\s*(\d+(?:\.\d+)?)\s*(?:℃|°C|度)?",
            re.I,
        ),
        CompareOp.GE,
        "℃",
        True,
    ),
    (
        "执行标准",
        re.compile(r"(?:执行标准|符合标准)[^。\n]{0,80}?(API\s*\d*|ANSI|ASME|GB/?T?\s*\d*|ISO\s*\d*)", re.I),
        CompareOp.IN,
        "",
        True,
    ),
    (
        "阀体材质",
        re.compile(r"(?:阀体材质|阀体材料)[^。\n]{0,60}?(316L?|304|WCB|WC6|QT450|双相钢)", re.I),
        CompareOp.IN,
        "",
        False,
    ),
    (
        "驱动方式",
        re.compile(r"(?:驱动方式|驱动型式)[^。\n]{0,40}?(电动|气动|液动|手动)", re.I),
        CompareOp.IN,
        "",
        False,
    ),
]

_STD_MAP = {
    "api": "API",
    "ansi": "ANSI",
    "asme": "ANSI",
    "gb": "GB",
    "iso": "ISO",
}
_MAT_MAP = {
    "316l": "316",
    "316": "316",
    "304": "304",
    "wcb": "WCB",
    "wc6": "WC6",
    "qt450": "QT450",
    "双相钢": "双相钢",
}
_WASTE_KW = ("废标", "否决投标", "无效投标", "不予受理", "视为放弃")
_RISK_KW = ("未按要求", "逾期", "未盖章", "未签字", "保证金")
_QUAL_KW = {
    "ISO9001": ("iso9001", "质量管理体系"),
    "API6D": ("api6d", "api 6d"),
    "API600": ("api600", "api 600"),
}


class TenderDocumentParser:
    """招标文件文本 → 结构化 ParsedTender。"""

    def parse(self, text: str, *, source: str = "") -> ParsedTender:
        normalized = re.sub(r"\s+", " ", text).strip()
        brief = self._parse_brief(text, normalized)
        requirements = self._parse_requirements(normalized)
        waste = self._extract_waste_clauses(text)
        for r in waste:
            brief.risks.append(RiskItem(clause=r[:200], level="高", summary=r[:120]))

        return ParsedTender(
            source=source,
            raw_text=text,
            brief=brief,
            requirements=requirements,
            waste_clauses=waste,
        )

    def _parse_brief(self, raw: str, norm: str) -> TenderBrief:
        title_m = re.search(r"(?:项目名称|招标项目)[:：\s]*([^\n]{4,80})", raw)
        deadline = self._parse_deadline(raw)
        quals = self._parse_qual_categories(norm)
        min_tr = self._parse_min_records(norm)
        industry = self._parse_industry(norm)
        points = self._key_points(norm)
        return TenderBrief(
            title=title_m.group(1).strip() if title_m else "",
            bid_deadline=deadline,
            required_qual_categories=quals,
            min_track_records=min_tr,
            industry_hint=industry,
            key_points=points,
        )

    def _parse_requirements(self, norm: str) -> list[TenderRequirement]:
        seen: set[str] = set()
        out: list[TenderRequirement] = []
        for param, pat, op, unit, critical in _TECH_RULES:
            for m in pat.finditer(norm):
                key = f"{param}:{m.group(0)[:40]}"
                if key in seen:
                    continue
                seen.add(key)
                req = self._match_to_requirement(param, m, op, unit, critical, norm)
                if req:
                    out.append(req)
        return out

    def _match_to_requirement(
        self,
        param: str,
        m: re.Match[str],
        op: CompareOp,
        unit: str,
        critical: bool,
        norm: str,
    ) -> TenderRequirement | None:
        raw = m.group(0)
        if param in ("公称压力", "公称通径", "工作温度"):
            val = float(m.group(1))
            return TenderRequirement(
                param=param, op=op, target_value=val, unit=unit,
                is_critical=critical, raw=raw,
            )
        if param == "执行标准":
            token = m.group(1).upper()
            std = "API" if "API" in token else _STD_MAP.get(token.lower()[:3], token[:6])
            return TenderRequirement(
                param=param, op=CompareOp.IN, target_set=[std],
                is_critical=critical, raw=raw,
            )
        if param == "阀体材质":
            mat_raw = m.group(1)
            mat = _MAT_MAP.get(mat_raw.lower(), mat_raw.upper())
            return TenderRequirement(
                param=param, op=CompareOp.IN, target_set=[mat],
                is_critical=critical, raw=raw,
            )
        if param == "驱动方式":
            drive = m.group(1)
            return TenderRequirement(
                param=param, op=CompareOp.IN, target_set=[drive],
                is_critical=critical, raw=raw,
            )
        return None

    @staticmethod
    def _parse_deadline(raw: str) -> date | None:
        m = re.search(
            r"(?:投标截止|递交截止|开标)[^。\n]{0,40}?(\d{4})[年\-/](\d{1,2})[月\-/](\d{1,2})",
            raw,
        )
        if not m:
            return None
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None

    @staticmethod
    def _parse_qual_categories(norm: str) -> list[str]:
        found: list[str] = []
        low = norm.lower()
        for cat, kws in _QUAL_KW.items():
            if any(k in low for k in kws):
                found.append(cat)
        return found

    @staticmethod
    def _parse_min_records(norm: str) -> int:
        m = re.search(
            r"(?:同类业绩|类似项目|供货业绩)[^。\n]{0,60}?(?:不少于|至少|≥|>=)\s*(\d+)\s*(?:项|个|条)",
            norm,
        )
        return int(m.group(1)) if m else 0

    @staticmethod
    def _parse_industry(norm: str) -> str:
        for ind in ("电力", "石化", "水务", "冶金", "核电", "化工"):
            if ind in norm:
                return ind
        return ""

    @staticmethod
    def _key_points(norm: str) -> list[str]:
        points: list[str] = []
        if "蒸汽" in norm or "STEAM" in norm.upper():
            points.append("介质含蒸汽,关注耐温与材质规则")
        if re.search(r"电动", norm):
            points.append("要求电动驱动,需核对执行机构供货范围")
        if "API" in norm.upper():
            points.append("执行标准含 API,需核对 API6D/API600 认证与型式试验")
        if not points:
            points.append("已抽取技术参数与废标条款,建议人工复核评分办法与商务条款")
        return points

    @staticmethod
    def _extract_waste_clauses(text: str) -> list[str]:
        clauses: list[str] = []
        for line in text.splitlines():
            s = line.strip()
            if len(s) < 8:
                continue
            if any(k in s for k in _WASTE_KW) or (
                any(k in s for k in _RISK_KW) and len(s) < 300
            ):
                clauses.append(s)
        return clauses[:30]
