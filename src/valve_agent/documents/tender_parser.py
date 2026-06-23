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
_WASTE_KW = ("废标", "否决投标", "无效投标", "不予受理", "视为无效", "视为放弃")
_RISK_KW = ("未按要求", "逾期", "未盖章", "未签字", "保证金", "密封不符", "资质证书", "串通投标", "弄虚作假")
_QUAL_KW = {
    "ISO9001": ("iso9001", "质量管理体系"),
    "API6D": ("api6d", "api 6d"),
    "API600": ("api600", "api 600"),
    "TS": ("ts认证", "特种设备制造许可", "压力管道"),
}

# 评分标准关键词
_SCORE_SECTION_KW = ("综合评分", "评标办法", "评分标准", "评分表", "评分细则")
_SCORE_ITEM_PAT = re.compile(
    r"([技商质售业绩服务报价术方案质量][^\n]{2,20})[^\d]*(\d{1,3})\s*分",
)


class TenderDocumentParser:
    """招标文件文本 → 结构化 ParsedTender。"""

    def parse(self, text: str, *, source: str = "") -> ParsedTender:
        normalized = re.sub(r"\s+", " ", text).strip()
        brief = self._parse_brief(text, normalized)
        requirements = self._parse_requirements(normalized)
        waste = self._extract_waste_clauses(text)
        # risks 只保留评分标准，不混入废标条款

        return ParsedTender(
            source=source,
            raw_text=text,
            brief=brief,
            requirements=requirements,
            waste_clauses=waste,
        )

    def _parse_brief(self, raw: str, norm: str) -> TenderBrief:
        title = self._extract_title(raw)
        deadline = self._parse_deadline(raw)
        quals = self._parse_qual_categories(norm)
        min_tr = self._parse_min_records(norm)
        industry = self._parse_industry(norm)
        points = self._key_points(norm)
        scoring = self._extract_scoring(raw, norm)
        return TenderBrief(
            title=title,
            bid_deadline=deadline,
            required_qual_categories=quals,
            min_track_records=min_tr,
            industry_hint=industry,
            key_points=points,
            risks=scoring,
        )

    @staticmethod
    def _extract_title(raw: str) -> str:
        """从招标文件中提取项目名称。"""
        # 方式1：明确的"项目名称："标记
        m = re.search(r"(?:项目名称|招标项目)[：:]\s*([^\n]{4,80})", raw)
        if m:
            return m.group(1).strip()
        # 方式2：文档第二行非空行（去掉空格后，标题文档通常第二行是项目名）
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        for line in lines[:5]:
            # 去除全角空格，长度合适，不含冒号，不是"招标文件"
            clean = re.sub(r'\s+', '', line)
            if 5 < len(clean) < 40 and '招标文件' not in clean and '编号' not in clean and '：' not in clean:
                return line.strip()
        return ""

    @staticmethod
    def _extract_scoring(raw: str, norm: str) -> list[RiskItem]:
        """提取评分标准（优先从管道符格式表格提取）。"""
        items: list[RiskItem] = []
        lines = raw.splitlines()
        in_score = False
        for i, line in enumerate(lines):
            s = line.strip()
            # 进入评分章节
            if re.search(r"评分项目.*分值|评标方法|综合评分", s):
                in_score = True
                continue
            if in_score:
                # 管道符格式的评分行：项目名称 | 分值 | 说明
                parts = [p.strip() for p in s.split("|")]
                if len(parts) >= 2:
                    try:
                        score_val = int(re.search(r"\d+", parts[1]).group())  # type: ignore
                        if 1 <= score_val <= 100:  # 合法分值范围
                            items.append(RiskItem(
                                clause=s[:120],
                                level="评分",
                                summary=f"{parts[0]}（{score_val}分）",
                            ))
                    except (AttributeError, ValueError, IndexError):
                        pass
                # 结束评分章节（遇到下一章/节，或超过合理行数）
                if re.match(r"第[五六七八九十]+章|^5\.2|^定标原则|^文件类目|^资质文件", s):
                    in_score = False
            if len(items) >= 8:
                break
        # fallback：从文本正则匹配
        if not items:
            for m in re.finditer(r"(技术[方案响应]*|商务报价|质量业绩|售后服务|业绩)\s*[：:，,]?\s*(\d+)\s*分", norm):
                items.append(RiskItem(
                    clause=m.group(0),
                    level="评分",
                    summary=f"{m.group(1)}（{m.group(2)}分）",
                ))
        return items[:8]

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
        # 额外：从表格行提取 DN/PN/温度/材质
        out.extend(self._extract_table_params(norm, seen))
        return out

    @staticmethod
    def _extract_table_params(norm: str, seen: set[str]) -> list[TenderRequirement]:
        """从管道符表格中提取型号参数行（DN/PN/温度）。"""
        extra: list[TenderRequirement] = []
        # 匹配 "型号 | 名称 | DN200 | PN40 | 介质/250℃ | ..." 格式
        row_pat = re.compile(
            r"[A-Z]\w+\s*\|\s*[^\|]+\|\s*(DN\s*\d+)\s*\|\s*(PN\s*\d+(?:\.\d+)?)\s*\|\s*[^/\|]+/(\d{2,3})\s*℃"
        )
        for m in row_pat.finditer(norm):
            dn_str = re.search(r"\d+", m.group(1))
            pn_str = re.search(r"\d+(?:\.\d+)?", m.group(2))
            temp_str = m.group(3)
            if not (dn_str and pn_str):
                continue
            dn, pn, temp = float(dn_str.group()), float(pn_str.group()), float(temp_str)
            for param, val, unit, crit in [
                ("公称通径", dn,  "mm",  False),
                ("公称压力", pn,  "bar", True),
                ("工作温度", temp,"℃",  True),
            ]:
                key = f"{param}:table:{val}"
                if key not in seen:
                    seen.add(key)
                    extra.append(TenderRequirement(
                        param=param, op=CompareOp.GE,
                        target_value=val, unit=unit,
                        is_critical=crit, raw=m.group(0)[:80],
                    ))
        # 同时用旧的 DN/PN/℃ 正则作补充
        old_pat = re.compile(r"DN\s*(\d+)[^\d]{1,10}PN\s*(\d+(?:\.\d+)?)[^\d]{1,20}(\d{2,3})\s*℃")
        for m in old_pat.finditer(norm):
            dn, pn, temp = m.group(1), m.group(2), m.group(3)
            for param, val, unit, crit in [
                ("公称通径", float(dn),  "mm",  False),
                ("公称压力", float(pn),  "bar", True),
                ("工作温度", float(temp),"℃",  True),
            ]:
                key = f"{param}:table:{val}"
                if key not in seen:
                    seen.add(key)
                    extra.append(TenderRequirement(
                        param=param, op=CompareOp.GE,
                        target_value=val, unit=unit,
                        is_critical=crit, raw=m.group(0),
                    ))
        return extra

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
            points.append("介质含蒸汽，关注耐温与材质规则")
        if re.search(r"电动", norm):
            points.append("要求电动驱动，需核对执行机构供货范围")
        if "API" in norm.upper():
            points.append("执行标准含 API，需核对 API6D/API600 认证与型式试验")
        m = re.search(r"保修[^。\n]{0,30}?(\d+)\s*(?:个月|年)", norm)
        if m:
            points.append(f"质保要求：{m.group(0).strip()}")
        m2 = re.search(r"交货[^。\n]{0,20}?(\d+)\s*(?:天|日|个月)", norm)
        if m2:
            points.append(f"交货期：{m2.group(0).strip()}")
        if not points:
            points.append("已抽取技术参数与废标条款，建议人工复核评分办法与商务条款")
        return points

    @staticmethod
    def _extract_waste_clauses(text: str) -> list[str]:
        """提取真正的废标条款（过滤掉章节标题和附件说明）。"""
        clauses: list[str] = []
        in_waste_section = False
        for line in text.splitlines():
            s = line.strip()
            if len(s) < 6:
                continue
            # 进入废标章节
            if re.search(r"(?:废标条款|无效投标|否决投标)", s) and len(s) < 20:
                in_waste_section = True
                continue
            # 退出废标章节（遇到下一章）
            if in_waste_section and re.match(r"第[二三四五六七八九十]+章", s):
                in_waste_section = False
            if in_waste_section:
                # 跳过章节标题和附件说明
                if re.match(r"^附件\d|^第[一二三四五六七八九]+章|^[一二三四五六七八九]、", s):
                    continue
                if len(s) > 10:
                    clauses.append(s)
            elif any(k in s for k in _WASTE_KW) and 15 < len(s) < 200:
                # 章节外的废标相关句子
                if not re.match(r"^附件|^第[一二三四五六七八九十]+章", s):
                    clauses.append(s)
        return list(dict.fromkeys(clauses))[:20]  # 去重
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


