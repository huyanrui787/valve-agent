"""valve-agent CLI —— 选型 / 报价 / 偏离表 / 端到端 demo。

体现方案两条主线("选型+报价"与"招标解析+自动应答")可在终端跑通。
所有命令离线可用(LLM 走 OfflineProvider)。
"""

from __future__ import annotations

from datetime import date

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .agents import BidAgent, QuoteAgent, QuoteRequestLine
from .engines import Verdict
from .engines.waste_bid import RiskLevel
from .knowledge import build_demo_kb
from .llm import ConditionParser
from .models import CompareOp, TenderRequirement

app = typer.Typer(
    help="阀门企业智能标书与报价 Agent — 确定性引擎 demo",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()

_VERDICT_STYLE = {
    Verdict.SATISFY: "green",
    Verdict.POSITIVE: "cyan",
    Verdict.NEGATIVE: "bold red",
    Verdict.UNKNOWN: "yellow",
}
_RISK_STYLE = {
    RiskLevel.OK: "green",
    RiskLevel.WARN: "yellow",
    RiskLevel.FAIL: "bold red",
}


def _money(x: float) -> str:
    return f"¥{x:,.2f}"


# --------------------------------------------------------------------------
# 渲染辅助
# --------------------------------------------------------------------------
def _render_selection(sel, show_rejections: bool = False) -> None:
    t = Table(title="选型结果(规则引擎,带选型依据)", show_lines=False)
    t.add_column("排名", justify="right")
    t.add_column("型号")
    t.add_column("名称")
    t.add_column("阀体/阀芯材质")
    t.add_column("依据(摘要)")
    for i, c in enumerate(sel.candidates, 1):
        t.add_row(
            str(i), c.product.code, c.product.name,
            f"{c.chosen_body_material}/{c.chosen_trim_material}",
            "; ".join(c.reasons[:3]) + " …",
        )
    console.print(t)
    if sel.material_notes:
        console.print("[dim]材质规则:" + " | ".join(sel.material_notes) + "[/dim]")
    if show_rejections and sel.rejections:
        rt = Table(title="淘汰记录(证据链)", show_lines=False)
        rt.add_column("型号")
        rt.add_column("步骤")
        rt.add_column("原因")
        for r in sel.rejections:
            rt.add_row(r.code, r.stage, r.reason)
        console.print(rt)


def _render_quote_line(ql, show_breakdown: bool = True) -> None:
    if show_breakdown:
        bt = Table(title=f"成本拆解 — {ql.product_code} DN{ql.dn}", show_lines=False)
        bt.add_column("项目")
        bt.add_column("材料")
        bt.add_column("数量", justify="right")
        bt.add_column("单价", justify="right")
        bt.add_column("金额", justify="right")
        for cl in ql.cost_lines:
            bt.add_row(
                cl.name, cl.material_key or "—",
                f"{cl.quantity:g}{cl.unit}",
                f"{cl.unit_price:,.2f}", f"{cl.amount:,.2f}")
        console.print(bt)
    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="bold")
    summary.add_column()
    summary.add_row("单台成本", _money(ql.unit_cost))
    summary.add_row("税前单价", _money(ql.pre_tax_unit_price))
    summary.add_row("含税单价", f"[bold]{_money(ql.unit_price)}[/bold]")
    summary.add_row("实际毛利率", f"{ql.margin:.1%}")
    summary.add_row("数量", str(ql.quantity))
    summary.add_row("整单金额", f"[bold green]{_money(ql.line_total)}[/bold green]")
    if ql.export_unit_price_cny:
        summary.add_row("出口单价(CNY)", _money(ql.export_unit_price_cny))
    summary.add_row("报价基准日", str(ql.price_basis))
    console.print(Panel(summary, title="报价(成本透明、毛利可控)", expand=False))
    for w in ql.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")


def _render_deviation(dt) -> None:
    t = Table(title=f"技术偏离表 — {dt.product_code} {dt.product_name}", show_lines=True)
    t.add_column("#", justify="right")
    t.add_column("参数")
    t.add_column("招标要求")
    t.add_column("产品能力")
    t.add_column("判定")
    t.add_column("关键", justify="center")
    t.add_column("建议/证据")
    for i in dt.items:
        style = _VERDICT_STYLE.get(i.verdict, "")
        detail = i.suggestion if i.suggestion else (i.evidence[0] if i.evidence else "")
        t.add_row(
            str(i.seq), i.param, i.requirement, i.product_capability,
            f"[{style}]{i.verdict.value}[/{style}]",
            "★" if i.is_critical else "",
            detail)
    console.print(t)
    console.print(
        f"[dim]统计:满足/正偏离 {len(dt.items)-dt.negative_count}/{dt.items.__len__()},"
        f"负偏离 {dt.negative_count},其中关键负偏离 "
        f"[bold red]{len(dt.critical_negatives)}[/bold red][/dim]")


def _render_report(report) -> None:
    t = Table(title="废标风险体检报告", show_lines=False)
    t.add_column("检查项")
    t.add_column("等级")
    t.add_column("说明")
    for i in report.items:
        style = _RISK_STYLE.get(i.level, "")
        t.add_row(i.name, f"[{style}]{i.level.value}[/{style}]", i.detail)
    console.print(t)
    overall = report.overall
    console.print(Panel(
        f"[{_RISK_STYLE[overall]}]总体:{overall.value}[/{_RISK_STYLE[overall]}]"
        f"  高风险 {len(report.fails)} 项,预警 {len(report.warns)} 项",
        expand=False))


# --------------------------------------------------------------------------
# 命令
# --------------------------------------------------------------------------
@app.command()
def select(
    spec: str = typer.Argument(..., help='工况描述,如 "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"'),
    top: int = typer.Option(3, help="返回候选数"),
    show_rejections: bool = typer.Option(False, "--rejections", help="显示淘汰记录"),
) -> None:
    """自然语言选型(四步规则引擎)。"""
    kb = build_demo_kb()
    agent = QuoteAgent(kb)
    try:
        cond = ConditionParser().parse(spec)
    except ValueError as e:
        console.print(f"[red]解析失败:{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[dim]解析工况:DN{cond.dn} PN{cond.pn_bar:g} {cond.medium.value} "
                  f"{cond.temp_c:g}℃ "
                  f"{cond.valve_type.value if cond.valve_type else '不限阀类'}[/dim]")
    sel = agent.selector.select(cond, top_n=top)
    _render_selection(sel, show_rejections=show_rejections)


@app.command()
def quote(
    spec: str = typer.Argument(..., help="工况描述"),
    qty: int = typer.Option(1, help="数量"),
    tier: str = typer.Option("C", help="客户等级 A/B/C"),
    export: bool = typer.Option(False, "--export", help="出口报价"),
    basis: str = typer.Option("", help="报价基准日 YYYY-MM-DD,默认今天"),
    no_breakdown: bool = typer.Option(False, "--no-breakdown", help="不显示成本拆解"),
) -> None:
    """选型 + BOM 成本核算 + 毛利定价,生成报价。"""
    kb = build_demo_kb()
    agent = QuoteAgent(kb)
    pb = date.fromisoformat(basis) if basis else None
    oc = agent.quote_text(spec, quantity=qty, customer_tier=tier, is_export=export,
                          price_basis=pb)
    if oc.error:
        console.print(f"[red]{oc.error}[/red]")
        if oc.selection:
            _render_selection(oc.selection, show_rejections=True)
        raise typer.Exit(1)
    console.print(f"[bold]选定型号:[/bold]{oc.quote.product_code} {oc.quote.product_name}")
    _render_quote_line(oc.quote, show_breakdown=not no_breakdown)
    if oc.history_hint:
        console.print(f"[dim]{oc.history_hint}[/dim]")


@app.command(name="bid-compliance")
def bid_compliance(
    spec: str = typer.Argument(..., help="工况描述(用于先选型再做应答)"),
    bid_date: str = typer.Option("", help="投标日 YYYY-MM-DD,默认今天"),
    industry: str = typer.Option("", help="行业,用于业绩匹配"),
) -> None:
    """对选定型号生成技术偏离表 + 废标自检(用内置示例招标要求)。"""
    kb = build_demo_kb()
    qa = QuoteAgent(kb)
    ba = BidAgent(kb)
    bd = date.fromisoformat(bid_date) if bid_date else None
    oc = qa.quote_text(spec, quantity=1)
    if oc.selection is None or oc.selection.best is None:
        console.print("[red]未选到型号,无法生成应答[/red]")
        raise typer.Exit(1)
    best = oc.selection.best
    reqs = _demo_requirements()
    pkg = ba.build_package(
        best.product, reqs, bid_date=bd, chosen_body=best.chosen_body_material,
        required_qual_categories=["ISO9001", "API6D"], min_track_records=3,
        industry=industry or None)
    _render_deviation(pkg.deviation_table)
    _render_report(pkg.compliance_report)
    console.print(f"[bold]可否投标:[/bold]"
                  f"{'[green]是[/green]' if pkg.can_bid else '[red]否(存在高风险废标项)[/red]'}")


@app.command()
def batch(
    csv_path: str = typer.Argument(..., help="询价表 CSV:每行 描述,数量"),
    tier: str = typer.Option("C", help="客户等级 A/B/C"),
    customer: str = typer.Option("", help="客户名称"),
    export: bool = typer.Option(False, "--export", help="出口报价"),
    basis: str = typer.Option("", help="报价基准日 YYYY-MM-DD"),
) -> None:
    """批量询价单处理:逐行选型报价,分钟级出整单(方案 4.1 批量询价)。"""
    import csv as _csv

    kb = build_demo_kb()
    agent = QuoteAgent(kb)
    pb = date.fromisoformat(basis) if basis else None
    lines: list[QuoteRequestLine] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in _csv.reader(f):
            if not row or row[0].strip().startswith("#"):
                continue
            text = row[0].strip()
            qty = int(row[1]) if len(row) > 1 and row[1].strip() else 1
            lines.append(QuoteRequestLine(text=text, quantity=qty))

    quote, outcomes = agent.quote_batch(
        lines, customer=customer, customer_tier=tier, is_export=export, price_basis=pb)

    t = Table(title=f"批量报价单 — {customer or '(未填客户)'}", show_lines=False)
    t.add_column("#", justify="right")
    t.add_column("询价描述")
    t.add_column("选定型号")
    t.add_column("数量", justify="right")
    t.add_column("含税单价", justify="right")
    t.add_column("小计", justify="right")
    t.add_column("毛利", justify="right")
    for i, oc in enumerate(outcomes, 1):
        if oc.quote is not None:
            q = oc.quote
            t.add_row(str(i), oc.input_text, q.product_code, str(q.quantity),
                      f"{q.unit_price:,.2f}", f"{q.line_total:,.2f}", f"{q.margin:.0%}")
        else:
            t.add_row(str(i), oc.input_text, f"[red]{oc.error}[/red]",
                      str(oc.quantity), "—", "—", "—")
    console.print(t)
    ok = sum(1 for o in outcomes if o.quote is not None)
    console.print(Panel.fit(
        f"成功 {ok}/{len(outcomes)} 行  整单合计 "
        f"[bold green]{_money(quote.total)}[/bold green]  "
        f"综合毛利 {quote.overall_margin:.1%}",
        title="整单汇总", border_style="green"))


def _demo_requirements() -> list[TenderRequirement]:
    """内置示例招标技术要求(演示用)。"""
    return [
        TenderRequirement(param="公称压力", op=CompareOp.GE, target_value=40,
                          unit="bar", is_critical=True),
        TenderRequirement(param="公称通径", op=CompareOp.GE, target_value=100,
                          unit="mm"),
        TenderRequirement(param="工作温度", op=CompareOp.GE, target_value=300,
                          unit="℃", is_critical=True),
        TenderRequirement(param="执行标准", op=CompareOp.IN, target_set=["API"],
                          is_critical=True),
        TenderRequirement(param="阀体材质", op=CompareOp.IN, target_set=["316"]),
        TenderRequirement(param="驱动方式", op=CompareOp.IN, target_set=["电动"]),
    ]


@app.command()
def demo(
    basis: str = typer.Option("2026-06-04", help="报价基准日"),
) -> None:
    """端到端演示:招标解析→选型→报价→偏离表→废标自检→闭环复用。"""
    from rich.rule import Rule

    kb = build_demo_kb()
    qa = QuoteAgent(kb)
    ba = BidAgent(kb)
    pb = date.fromisoformat(basis)

    console.print(Panel.fit(
        "[bold]阀门企业智能标书与报价 Agent — 端到端演示[/bold]\n"
        "两个 Agent + 共享知识底座;规则保准确、模型保表达;全程离线可跑",
        border_style="blue"))

    # ---- 哇时刻一:自然语言秒选型 ----
    console.print(Rule("哇时刻一 · 自然语言选型(报价 Agent)"))
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"
    console.print(f"输入询价:[italic]{spec}[/italic]")
    oc = qa.quote_text(spec, quantity=10, customer_tier="A", price_basis=pb)
    _render_selection(oc.selection)

    # ---- 哇时刻二:成本拆解秒报价 ----
    console.print(Rule("哇时刻二 · BOM 成本核算 + 毛利定价"))
    console.print(f"[bold]选定:[/bold]{oc.quote.product_code} {oc.quote.product_name}  "
                  f"(客户等级 A,数量 10)")
    _render_quote_line(oc.quote)
    if oc.history_hint:
        console.print(f"[dim]{oc.history_hint}[/dim]")

    # ---- 哇时刻三:自动技术偏离表 + 废标自检 ----
    console.print(Rule("哇时刻三 · 技术偏离表 + 废标自检(标书 Agent)"))
    best = oc.selection.best
    reqs = _demo_requirements()
    console.print(f"招标技术要求 {len(reqs)} 条 → 自动逐条应答(负偏离标红、关键项★)")
    pkg = ba.build_package(
        best.product, reqs, bid_date=pb, chosen_body=best.chosen_body_material,
        required_qual_categories=["ISO9001", "API6D"], min_track_records=3,
        industry="电力")
    _render_deviation(pkg.deviation_table)
    _render_report(pkg.compliance_report)

    # ---- 哇时刻四:闭环 + 改型消除废标 ----
    console.print(Rule("哇时刻四 · 闭环复用 + 改型消除废标风险"))
    console.print("上一型号关键项(温度 300℃)负偏离 → 极可能废标。"
                  "Agent 自动改选更高等级型号重选:")
    spec2 = "闸阀 DN200 PN100 蒸汽 350℃ 电动 API 316"
    console.print(f"重选工况:[italic]{spec2}[/italic]")
    oc2 = qa.quote_text(spec2, quantity=10, customer_tier="A", price_basis=pb)
    if oc2.selection and oc2.selection.best:
        best2 = oc2.selection.best
        console.print(f"[green]改选型号:[/green]{best2.product.code} {best2.product.name}")
        pkg2 = ba.build_package(
            best2.product, _demo_requirements(), bid_date=pb,
            chosen_body=best2.chosen_body_material,
            required_qual_categories=["ISO9001", "API6D"], min_track_records=3,
            industry="电力")
        _render_deviation(pkg2.deviation_table)
        tech_ok = not pkg2.deviation_table.critical_negatives
        console.print(
            f"[bold]技术响应:[/bold]"
            f"{'[green]关键项全部满足/正偏离,技术废标风险已消除[/green]' if tech_ok else '[red]仍有关键负偏离[/red]'}")
        # 区分技术结论与商务结论:改型只解决技术废标,商务项(业绩数量等)需另行补足
        biz_fails = [f for f in pkg2.compliance_report.fails
                     if "技术响应" not in f.name]
        if biz_fails:
            console.print(
                "[yellow]仍存商务待办(不影响技术应答,需业务侧补足):[/yellow] "
                + "; ".join(f.detail for f in biz_fails))
        console.print(f"[bold]整体可投标:[/bold]"
                      f"{'[green]是[/green]' if pkg2.can_bid else '[yellow]需先补足上述商务项[/yellow]'}")
        console.print(f"[dim]改型后整单报价:{_money(oc2.quote.line_total)} "
                      f"(含税单价 {_money(oc2.quote.unit_price)},毛利 {oc2.quote.margin:.1%})"
                      f" — 报价同源回流标书,一次确定、两处复用[/dim]")

    console.print(Rule("演示结束"))
    console.print(Panel.fit(
        "确定性核心已落地:选型/报价/偏离判定全程可解释、带证据链。\n"
        "LLM 表达层(方案撰写、话术润色、NL 解析)以可插拔 Provider 接入,"
        "当前为离线 stub,生产可替换为私有化国产大模型。",
        border_style="green"))


if __name__ == "__main__":
    app()
