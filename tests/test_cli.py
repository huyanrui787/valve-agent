"""CLI 烟雾测试(typer CliRunner)。"""

from __future__ import annotations

from typer.testing import CliRunner

from valve_agent.cli import app

runner = CliRunner()


def test_cli_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "select" in r.stdout
    assert "quote" in r.stdout


def test_cli_select():
    r = runner.invoke(app, ["select", "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"])
    assert r.exit_code == 0
    assert "Q41F-40P" in r.stdout


def test_cli_quote():
    r = runner.invoke(app, ["quote", "球阀 DN200 PN40 蒸汽 250℃ 电动 316",
                            "--qty", "10", "--tier", "A"])
    assert r.exit_code == 0
    assert "整单金额" in r.stdout


def test_cli_quote_no_match_exits_nonzero():
    r = runner.invoke(app, ["quote", "球阀 DN50 PN600 水 20℃"])
    assert r.exit_code == 1


def test_cli_bid_compliance():
    r = runner.invoke(app, ["bid-compliance",
                            "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316",
                            "--industry", "电力"])
    assert r.exit_code == 0
    assert "偏离表" in r.stdout
    assert "废标风险体检报告" in r.stdout


def test_cli_demo_runs():
    r = runner.invoke(app, ["demo"])
    assert r.exit_code == 0
    assert "哇时刻一" in r.stdout
    assert "演示结束" in r.stdout


def test_cli_batch(tmp_path):
    csv = tmp_path / "inq.csv"
    csv.write_text(
        "球阀 DN200 PN40 蒸汽 250℃ 电动 316,10\n"
        "蝶阀 DN300 PN16 水 80℃ 电动,20\n"
        "球阀 DN50 PN600 水 20℃,3\n",
        encoding="utf-8",
    )
    r = runner.invoke(app, ["batch", str(csv), "--customer", "测试客户"])
    assert r.exit_code == 0
    assert "整单合计" in r.stdout
    assert "成功 2/3" in r.stdout
