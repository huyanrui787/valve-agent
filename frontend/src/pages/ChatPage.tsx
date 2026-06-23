import { useEffect, useRef, useState } from "react";
import {
  fetchChatStatus,
  streamChat,
  streamChatConfirm,
} from "../api/client";
import type { AgentEvent } from "../types";
import { ToolCard } from "../components/ToolCard";
import { ArtifactCanvas } from "../components/ArtifactCanvas";
import { toolLabel } from "../components/toolMeta";

type Turn =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "tool"; call: AgentEvent; result?: AgentEvent; pending?: boolean }
  | { kind: "error"; text: string; downgrade?: boolean };

interface Pending {
  sessionId: string;
  callId: string;
  tool: string;
  prompt: string;
}

const SAMPLES = [
  "某电厂采购球阀 DN200 PN40 蒸汽 250℃ 电动 API 316,10 台,A 级客户。先报价,再看技术上能不能应标",
  "蝶阀 DN300 PN16 水 80℃ 电动,报价 20 台,B 级客户",
  "帮我查一下电力行业的历史业绩",
];

export function ChatPage() {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [qty, setQty] = useState("");
  const [tier, setTier] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string>("");
  const [pending, setPending] = useState<Pending | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChatStatus()
      .then((s) => setAvailable(s.available))
      .catch(() => setAvailable(false));
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [turns]);

  const artifacts = turns
    .filter((t): t is Extract<Turn, { kind: "tool" }> => t.kind === "tool")
    .filter((t) => t.result && t.result.ok && !(t.result.result as any)?.error)
    .map((t) => t.result as AgentEvent)
    .reverse();

  function handleEvent(ev: AgentEvent) {
    switch (ev.type) {
      case "session":
        if (ev.session_id) setSessionId(ev.session_id);
        break;
      case "thinking":
        if (ev.text?.trim())
          setTurns((ts) => [...ts, { kind: "assistant", text: ev.text! }]);
        break;
      case "tool_call":
        setTurns((ts) => [...ts, { kind: "tool", call: ev }]);
        break;
      case "tool_result":
        setTurns((ts) =>
          ts.map((t) =>
            t.kind === "tool" && t.call.call_id === ev.call_id && !t.result
              ? { ...t, result: ev, pending: false }
              : t,
          ),
        );
        break;
      case "await_confirm":
        setTurns((ts) =>
          ts.map((t) =>
            t.kind === "tool" && t.call.call_id === ev.call_id
              ? { ...t, pending: true }
              : t,
          ),
        );
        setPending({
          sessionId,
          callId: ev.call_id ?? "",
          tool: ev.tool ?? "",
          prompt: ev.prompt ?? "",
        });
        break;
      case "message":
        if (ev.text?.trim())
          setTurns((ts) => [...ts, { kind: "assistant", text: ev.text! }]);
        break;
      case "error":
        setTurns((ts) => [
          ...ts,
          { kind: "error", text: ev.message ?? "出错了", downgrade: ev.downgrade },
        ]);
        break;
    }
  }

  function buildMessage(raw: string): string {
    let msg = raw.trim();
    const extras: string[] = [];
    if (qty.trim()) extras.push(`数量 ${qty.trim()} 台`);
    if (tier.trim()) extras.push(`${tier.trim()} 级客户`);
    if (extras.length > 0) msg = `${msg}，${extras.join("，")}`;
    return msg;
  }

  async function send() {
    const msg = buildMessage(input);
    if (!msg || busy) return;
    setInput("");
    setTurns((ts) => [...ts, { kind: "user", text: msg }]);
    setBusy(true);
    try {
      await streamChat(msg, handleEvent);
    } catch (e) {
      setTurns((ts) => [
        ...ts,
        { kind: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function resolvePending(approved: boolean) {
    if (!pending) return;
    const p = pending;
    setPending(null);
    setBusy(true);
    try {
      await streamChatConfirm(p.sessionId, p.callId, approved, handleEvent);
    } catch (e) {
      setTurns((ts) => [
        ...ts,
        { kind: "error", text: e instanceof Error ? e.message : String(e) },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (available === false) {
    return <Downgrade />;
  }

  return (
    <div className="chat-layout">
      <section className="chat-col">
        <div className="chat-scroll" ref={scrollRef}>
          {turns.length === 0 && <Welcome onPick={(s) => setInput(s)} />}
          {turns.map((t, i) => (
            <TurnView key={i} turn={t} />
          ))}
          {busy && !pending && <div className="typing">助手思考中…</div>}
          {pending && (
            <ConfirmBar
              prompt={pending.prompt}
              tool={pending.tool}
              onApprove={() => resolvePending(true)}
              onDecline={() => resolvePending(false)}
            />
          )}
        </div>
        <div className="chat-input-area">
          <div className="quick-params">
            <div className="quick-field">
              <label>数量</label>
              <input
                type="number"
                min={1}
                placeholder="台数"
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                disabled={busy}
              />
            </div>
            <div className="quick-field">
              <label>客户等级</label>
              <select value={tier} onChange={(e) => setTier(e.target.value)} disabled={busy}>
                <option value="">AI 推断</option>
                <option value="A">A 级</option>
                <option value="B">B 级</option>
                <option value="C">C 级</option>
              </select>
            </div>
          </div>
          <div className="chat-input">
            <textarea
              value={input}
              placeholder="描述采购需求，例如：某电厂球阀 DN200 PN40 蒸汽 250℃，报价 10 台并看能否应标"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              disabled={busy}
            />
            <button className="btn" onClick={send} disabled={busy || !input.trim()}>
              发送
            </button>
          </div>
        </div>
      </section>
      <section className="canvas-col">
        <div className="canvas-head">报价产物</div>
        <ArtifactCanvas artifacts={artifacts} />
      </section>
    </div>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  if (turn.kind === "user")
    return <div className="bubble user">{turn.text}</div>;
  if (turn.kind === "assistant")
    return <div className="bubble assistant">{turn.text}</div>;
  if (turn.kind === "error")
    return (
      <div className="bubble error-bubble">
        {turn.text}
        {turn.downgrade && (
          <div className="muted small">
            可改用左侧「标书应答」等页继续工作。
          </div>
        )}
      </div>
    );
  return <ToolCard call={turn.call} result={turn.result} pending={turn.pending} />;
}

function ConfirmBar({
  prompt,
  tool,
  onApprove,
  onDecline,
}: {
  prompt: string;
  tool: string;
  onApprove: () => void;
  onDecline: () => void;
}) {
  const meta = toolLabel(tool);
  return (
    <div className="confirm-bar">
      <span>
        {meta.icon} {prompt || `将执行写操作「${meta.label}」`}
      </span>
      <div className="confirm-actions">
        <button className="btn" onClick={onApprove}>
          确认执行
        </button>
        <button className="btn secondary" onClick={onDecline}>
          取消
        </button>
      </div>
    </div>
  );
}

function Welcome({ onPick }: { onPick: (s: string) => void }) {
  return (
    <div className="welcome">
      <h2>智能报价</h2>
      <p className="muted">
        一句话说需求，我会自动选型、报价、做技术偏离表与废标自检——结果实时显示在右侧画布。
      </p>
      <div className="samples">
        {SAMPLES.map((s) => (
          <button key={s} className="sample" onClick={() => onPick(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Downgrade() {
  return (
    <div>
      <h1 className="page-title">智能报价</h1>
      <p className="page-desc">对话式 Agent 需要接入真实大模型。</p>
      <div className="card">
        <p>
          当前未检测到可用大模型（<code>DASHSCOPE_API_KEY</code> 未配置）。
          对话式编排依赖模型做多步规划，无法用离线 stub 驱动。
        </p>
        <p className="muted">
          配置 <code>DASHSCOPE_API_KEY</code> 后重启 valve-api 即可启用。
        </p>
      </div>
    </div>
  );
}

