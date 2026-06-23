"""ReAct 规划循环 —— Agent 运行时内核(对应方案 12.4)。

对话 → 模型规划 → 调工具 → 观察结果回喂 → 决定继续调或给最终答复。
全程以事件流(events.py)产出,既驱动前端流式渲染,也作审计留痕。

控制项(ReAct 必备):
  - MAX_STEPS 防失控
  - 同工具同参数去重,防原地打转
  - 工具异常作为观察结果回喂,让模型自我纠正而非整体崩溃
  - 写工具命中确认门:产出 await_confirm 事件后暂停,等用户放行(见 ChatSession.confirm)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from ..llm.base import ChatLLMProvider, ChatMessage, ToolCall
from .events import (
    AgentEvent,
    AwaitConfirmEvent,
    ErrorEvent,
    MessageEvent,
    ThinkingEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from .tools import ToolRegistry

MAX_STEPS = 8

DEFAULT_SYSTEM = (
    "你是阀门企业的智能销售/投标助手。你可以调用工具完成选型、报价、技术偏离表、"
    "废标自检、知识检索、导出与同步等任务。\n"
    "重要规则:\n"
    "1. 所有数值结果(价格、毛利、判定)必须来自工具返回,严禁自己编造数字或参数。\n"
    "2. 一个请求可连续调用多个工具(如先选型再报价再做应标分析),拿到结果后再汇总。\n"
    "3. 导出/同步等写操作会先请用户确认,你正常发起调用即可。\n"
    "4. 最终用简洁中文向用户汇报结论,并提示关键风险(如关键负偏离可能废标)。"
)


def _args_key(name: str, arguments: dict) -> str:
    return name + "|" + json.dumps(arguments, sort_keys=True, ensure_ascii=False)


class ChatSession:
    """一个对话会话:持有历史与工具表,驱动 ReAct 循环。

    用法:
        session = ChatSession(llm, registry)
        for ev in session.run("帮我报价..."):
            ...   # 消费事件
        # 若产出 await_confirm,前端确认后:
        for ev in session.confirm(call_id, approved=True):
            ...
    """

    def __init__(
        self,
        llm: ChatLLMProvider,
        registry: ToolRegistry,
        *,
        system: str = DEFAULT_SYSTEM,
        max_steps: int = MAX_STEPS,
    ) -> None:
        self.llm = llm
        self.registry = registry
        self.system = system
        self.max_steps = max_steps
        self.messages: list[ChatMessage] = []
        self._seen: set[str] = set()
        self._step = 0
        # 挂起的写操作:call_id -> (ToolCall)
        self._pending: dict[str, ToolCall] = {}

    # ------------------------------------------------------------------
    def run(self, user_input: str) -> Iterator[AgentEvent]:
        """处理一条用户输入,流式产出事件,直到给出最终答复或命中确认门。"""
        self.messages.append(ChatMessage(role="user", content=user_input))
        yield from self._loop()

    def confirm(self, call_id: str, approved: bool) -> Iterator[AgentEvent]:
        """用户对某个挂起的写操作做出确认 / 拒绝后,继续推进循环。"""
        call = self._pending.pop(call_id, None)
        if call is None:
            yield ErrorEvent(step=self._step, message=f"无待确认的工具调用:{call_id}")
            return
        if approved:
            yield from self._execute_call(call)
        else:
            # 拒绝:把"用户拒绝"作为观察结果回喂,让模型换条路
            self.messages.append(ChatMessage(
                role="tool", tool_call_id=call.id, name=call.name,
                content=json.dumps({"declined": True,
                                    "reason": "用户拒绝了该写操作"}, ensure_ascii=False)))
            yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                  ok=False, error="用户拒绝")
        # 若已无其它挂起项,继续循环
        if not self._pending:
            yield from self._loop()

    # ------------------------------------------------------------------
    def _loop(self) -> Iterator[AgentEvent]:
        """ReAct 主循环。"""
        while self._step < self.max_steps:
            self._step += 1
            try:
                result = self.llm.chat(
                    self.messages, tools=self.registry.schemas(), system=self.system)
            except Exception as e:  # 模型调用失败:报错并终止本轮
                yield ErrorEvent(step=self._step, message=f"模型调用失败:{e}")
                return

            if not result.is_tool_calls:
                # 最终文本答复
                self.messages.append(ChatMessage(role="assistant", content=result.content))
                yield MessageEvent(step=self._step, text=result.content)
                return

            # 模型要求调用工具:先记账到历史(assistant + tool_calls)
            if result.content:
                yield ThinkingEvent(step=self._step, text=result.content)
            self.messages.append(ChatMessage(
                role="assistant", content=result.content, tool_calls=result.tool_calls))

            # 逐个处理工具调用;写工具命中确认门则暂停
            hit_gate = False
            for call in result.tool_calls:
                tool = self.registry.get(call.name)
                if tool is None:
                    self._feed_tool_result(call, {"error": f"未知工具:{call.name}"})
                    yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                          ok=False, error="未知工具")
                    continue

                yield ToolCallEvent(step=self._step, call_id=call.id, tool=call.name,
                                    arguments=call.arguments, is_write=tool.is_write)

                if tool.is_write:
                    self._pending[call.id] = call
                    hit_gate = True
                    yield AwaitConfirmEvent(
                        step=self._step, call_id=call.id, tool=call.name,
                        arguments=call.arguments,
                        prompt=f"将执行写操作「{call.name}」,确认?")
                    continue

                yield from self._execute_call(call)

            if hit_gate:
                # 有写操作待确认:暂停循环,交还控制权给前端
                return
            # 否则继续下一轮(模型基于工具结果决定继续调或收尾)

        # 超出步数上限
        yield ErrorEvent(step=self._step,
                         message=f"已达最大推理步数 {self.max_steps},请拆分需求或稍后重试")

    # ------------------------------------------------------------------
    def _execute_call(self, call: ToolCall) -> Iterator[AgentEvent]:
        """执行一个(只读或已确认的写)工具调用,并把结果回喂历史。"""
        tool = self.registry.get(call.name)
        if tool is None:
            self._feed_tool_result(call, {"error": f"未知工具:{call.name}"})
            yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                  ok=False, error="未知工具")
            return

        # 去重:同工具同参数已执行过,直接提示,避免原地打转
        key = _args_key(call.name, call.arguments)
        if key in self._seen:
            note = {"note": "该工具以相同参数已调用过,请基于已有结果作答"}
            self._feed_tool_result(call, note)
            yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                  ok=True, result=note)
            return
        self._seen.add(key)

        try:
            result: Any = tool.run(call.arguments)
            self._feed_tool_result(call, result)
            yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                  ok=True, result=result)
        except Exception as e:  # 工具异常作为观察结果回喂,让模型自我纠正
            err = {"error": f"{type(e).__name__}: {e}"}
            self._feed_tool_result(call, err)
            yield ToolResultEvent(step=self._step, call_id=call.id, tool=call.name,
                                  ok=False, error=str(e))

    def _feed_tool_result(self, call: ToolCall, result: Any) -> None:
        self.messages.append(ChatMessage(
            role="tool", tool_call_id=call.id, name=call.name,
            content=json.dumps(result, ensure_ascii=False, default=str)))
