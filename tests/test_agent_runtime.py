"""Agent 运行时(对话式 Agent 2.0)单测 —— 全程用 MockChatProvider,不调真实 API。

覆盖:工具注册表、单步报价、多步编排(选型→报价→应标)、
工具异常回喂、同参去重、写操作确认门(放行 / 拒绝)、超步数保护。
"""

from __future__ import annotations

from valve_agent.agent import ChatSession, build_default_registry
from valve_agent.llm import ChatResult, MockChatProvider, ToolCall


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------
def test_registry_has_expected_tools(kb):
    reg = build_default_registry(kb)
    names = set(reg.names())
    assert {"select_valve", "quote", "assess_compliance", "check_waste_bid",
            "rag_search", "export_quote_docx", "sync_crm"} <= names
    # 写工具被标记
    assert reg.get("export_quote_docx").is_write is True
    assert reg.get("sync_crm").is_write is True
    assert reg.get("quote").is_write is False
    # 每个工具都有合法的 OpenAI 风格声明
    for s in reg.schemas():
        assert s["type"] == "function"
        assert "name" in s["function"] and "parameters" in s["function"]


def test_quote_tool_returns_engine_numbers(kb):
    """工具结果的数值来自引擎(不是模型编造)。"""
    reg = build_default_registry(kb)
    res = reg.get("quote").run({"spec": "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316",
                                "quantity": 10, "customer_tier": "A"})
    assert res["product_code"] == "Q41F-40P"
    assert res["line_total"] > 0
    assert 0 < res["margin"] < 1


# ---------------------------------------------------------------------------
# 单步:模型调一次工具后收尾
# ---------------------------------------------------------------------------
def test_single_tool_then_answer(kb):
    reg = build_default_registry(kb)
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="quote",
                   arguments={"spec": "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316",
                              "quantity": 10, "customer_tier": "A"})]),
        ChatResult(content="已完成报价。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("给某电厂报个价"))
    types = [e.type for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert events[-1].type == "message"
    assert events[-1].text == "已完成报价。"
    # 工具结果已回喂历史(role=tool)
    assert any(m.role == "tool" for m in session.messages)


# ---------------------------------------------------------------------------
# 多步:选型 → 报价 → 应标,连续三次工具调用再收尾
# ---------------------------------------------------------------------------
def test_multi_step_orchestration(kb):
    reg = build_default_registry(kb)
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="select_valve",
                                        arguments={"spec": spec})]),
        ChatResult(tool_calls=[ToolCall(id="c2", name="quote",
                                        arguments={"spec": spec, "quantity": 10})]),
        ChatResult(tool_calls=[ToolCall(id="c3", name="assess_compliance",
                   arguments={"spec": spec, "requirements": [
                       {"param": "工作温度", "op": ">=", "target_value": 300,
                        "unit": "℃", "is_critical": True}]})]),
        ChatResult(content="选型、报价、应标分析完成,关键项温度负偏离,提示废标风险。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("报价并看能否应标"))
    tool_calls = [e for e in events if e.type == "tool_call"]
    assert [e.tool for e in tool_calls] == ["select_valve", "quote", "assess_compliance"]
    assert events[-1].type == "message"
    # 模型被调用 4 次(3 次出工具 + 1 次收尾)
    assert len(mock.calls) == 4


# ---------------------------------------------------------------------------
# 工具异常作为观察结果回喂,不崩溃
# ---------------------------------------------------------------------------
def test_tool_error_is_fed_back(kb):
    reg = build_default_registry(kb)
    # spec 缺 DN,ConditionParser 抛 ValueError → select_valve 内部异常
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="select_valve",
                                        arguments={"spec": "球阀 没有口径"})]),
        ChatResult(content="抱歉,工况缺少通径,请补充 DN。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("选个阀"))
    tr = [e for e in events if e.type == "tool_result"]
    assert tr and tr[0].ok is False
    assert events[-1].type == "message"
    # 错误以 role=tool 回喂,供模型纠正
    assert any(m.role == "tool" and "error" in m.content.lower() or "通径" in m.content
               for m in session.messages)


# ---------------------------------------------------------------------------
# 同工具同参数去重
# ---------------------------------------------------------------------------
def test_duplicate_tool_call_dedup(kb):
    reg = build_default_registry(kb)
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316"
    args = {"spec": spec, "quantity": 1}
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="c1", name="quote", arguments=args)]),
        ChatResult(tool_calls=[ToolCall(id="c2", name="quote", arguments=args)]),
        ChatResult(content="完成。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("报价"))
    results = [e for e in events if e.type == "tool_result"]
    # 第二次相同调用被去重,结果里带 note
    assert any(isinstance(r.result, dict) and "note" in r.result for r in results)


# ---------------------------------------------------------------------------
# 写操作确认门:放行
# ---------------------------------------------------------------------------
def test_write_gate_approve(kb):
    reg = build_default_registry(kb)
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 316"
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="w1", name="export_quote_docx",
                                        arguments={"spec": spec, "quantity": 2})]),
        ChatResult(content="已导出报价单。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("导出报价单"))
    # 命中确认门,暂停(无 message,出现 await_confirm)
    assert events[-1].type == "await_confirm"
    assert events[-1].call_id == "w1"
    # 确认门暂停时,写工具尚未执行
    assert not any(e.type == "tool_result" for e in events)

    # 用户放行 → 执行写工具并收尾
    after = list(session.confirm("w1", approved=True))
    types = [e.type for e in after]
    assert "tool_result" in types
    tr = [e for e in after if e.type == "tool_result"][0]
    assert tr.ok is True and tr.result["path"].endswith(".docx")
    assert after[-1].type == "message"


# ---------------------------------------------------------------------------
# 写操作确认门:拒绝
# ---------------------------------------------------------------------------
def test_write_gate_decline(kb):
    reg = build_default_registry(kb)
    spec = "球阀 DN200 PN40 蒸汽 250℃ 电动 316"
    mock = MockChatProvider([
        ChatResult(tool_calls=[ToolCall(id="w1", name="sync_crm",
                                        arguments={"spec": spec, "customer": "某电厂"})]),
        ChatResult(content="好的,已取消同步。"),
    ])
    session = ChatSession(mock, reg)
    events = list(session.run("同步到CRM"))
    assert events[-1].type == "await_confirm"

    after = list(session.confirm("w1", approved=False))
    tr = [e for e in after if e.type == "tool_result"][0]
    assert tr.ok is False and tr.error == "用户拒绝"
    assert after[-1].type == "message"
    # 拒绝信息回喂历史
    assert any(m.role == "tool" and "declined" in m.content for m in session.messages)


# ---------------------------------------------------------------------------
# 超步数保护
# ---------------------------------------------------------------------------
def test_max_steps_guard(kb):
    reg = build_default_registry(kb)
    # 模型每轮都要求一个新工具调用(每次参数不同避免去重),触发步数上限
    script = [
        ChatResult(tool_calls=[ToolCall(id=f"c{i}", name="rag_search",
                                        arguments={"query": f"问题{i}"})])
        for i in range(10)
    ]
    mock = MockChatProvider(script)
    session = ChatSession(mock, reg, max_steps=3)
    events = list(session.run("不停检索"))
    assert events[-1].type == "error"
    assert "最大推理步数" in events[-1].message
