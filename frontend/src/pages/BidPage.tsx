import { useCallback, useReducer, useRef, useState } from "react";
import { downloadBidDocx, postTenderBid, saveBlob } from "../api/client";
import type { BidPackage, TenderBidResponse } from "../types";
import {
  DEFAULT_SECTIONS,
  docReducer,
  initDoc,
} from "./BidDoc";

// ─── 对话 turn 类型 ───────────────────────────────────────────────
type Turn =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "error"; text: string };

const SAMPLES = [
  "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316，生成完整投标应答包",
  "蝶阀 DN300 PN16 水 80℃ 电动，有招标文件，先做偏离表再出技术方案",
  "截止阀 DN100 PN16 化工介质，重点查废标风险，帮我完善质量保证章节",
];

// ─── 辅助：从 BidPackage 生成各章节内容 ──────────────────────────
function buildDeviationContent(pkg: BidPackage): string {
  const rows = (pkg.deviation_table?.items ?? []).map((it) => {
    const flag = it.is_critical ? " ★" : "";
    return `| ${it.seq} | ${it.param}${flag} | ${it.requirement} | ${it.product_capability} | ${it.verdict} |`;
  });
  if (rows.length === 0) return "_（无偏离项）_";
  return [
    "| # | 参数 | 招标要求 | 产品能力 | 判定 |",
    "|---|------|----------|----------|------|",
    ...rows,
  ].join("\n");
}

function buildWasteContent(pkg: BidPackage): string {
  return (pkg.compliance_report?.items ?? [])
    .map((it) => `**[${it.level}]** ${it.name}\n${it.detail}`)
    .join("\n\n") || "_（无风险项）_";
}

function buildRecordsContent(pkg: BidPackage): string {
  const recs = (pkg as any).matched_records ?? [];
  if (recs.length === 0) return "_（暂无匹配业绩）_";
  return recs
    .map((r: any) =>
      `- **${r.project_name}** · ${r.customer} · ${r.valve_type} · ${r.contract_date} · 约 ${(r.amount / 1e4).toFixed(0)} 万元`
    )
    .join("\n");
}

// ─── 主组件 ──────────────────────────────────────────────────────
export function BidPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [doc, dispatch] = useReducer(docReducer, undefined, initDoc);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportSections, setExportSections] = useState<Set<string>>(
    new Set(DEFAULT_SECTIONS.map((s) => s.id))
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const editorRef = useRef<HTMLDivElement>(null);

  const activeSection = doc.sections.find((s) => s.id === doc.activeId);

  function scrollBottom() {
    setTimeout(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight }), 50);
  }

  function applyResult(r: TenderBidResponse) {
    const pkg = r.package;
    if (!pkg) return;
    const canBid = !(pkg.compliance_report?.items ?? []).some((i) => i.level === "高风险");
    dispatch({
      type: "SET_PARAMS",
      params: {
        productCode: pkg.product_code, productName: pkg.product_name,
        dn: 0, pn: 0, medium: "", temp: "", drive: "", material: "",
        deviationCount: pkg.deviation_table?.items?.length ?? 0,
        criticalNegative: pkg.deviation_table?.critical_negatives?.length ?? 0,
        canBid,
      },
    });
    dispatch({ type: "SET_CONTENT", id: "deviation", content: buildDeviationContent(pkg) });
    dispatch({ type: "SET_CONTENT", id: "waste",    content: buildWasteContent(pkg) });
    dispatch({ type: "SET_CONTENT", id: "proposal", content: pkg.tech_proposal ?? "" });
    dispatch({ type: "SET_CONTENT", id: "records",  content: buildRecordsContent(pkg) });
    dispatch({ type: "SET_STATUS",  id: "quality",  status: "empty" });
    dispatch({ type: "SET_ACTIVE",  id: "deviation" });
  }

  async function send() {
    const msg = input.trim();
    if (!msg || busy) return;
    setInput("");
    const displayMsg = file ? `${msg}（附件：${file.name}）` : msg;
    setTurns((ts) => [...ts, { kind: "user", text: displayMsg }]);
    setBusy(true);
    scrollBottom();
    const isRefine = doc.params !== null;
    const targetSection = isRefine ? detectTargetSection(msg) : null;
    try {
      if (targetSection) {
        dispatch({ type: "SET_STATUS", id: targetSection, status: "generating" });
        const res = await fetch("/api/chat", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: msg }),
        });
        if (!res.ok) throw new Error(`${res.status}`);
        const data = await res.json();
        const text = data.content ?? data.text ?? JSON.stringify(data);
        dispatch({ type: "SET_CONTENT", id: targetSection, content: text });
        dispatch({ type: "SET_ACTIVE",  id: targetSection });
        setTurns((ts) => [...ts, { kind: "assistant", text: `已更新「${sectionTitle(targetSection)}」章节。` }]);
      } else {
        const r = await postTenderBid(msg, file);
        applyResult(r);
        const pkg = r.package;
        if (pkg) {
          const canBid = !(pkg.compliance_report?.items ?? []).some((i) => i.level === "高风险");
          setTurns((ts) => [...ts, {
            kind: "assistant",
            text: [
              `已生成标书：${pkg.product_code} ${pkg.product_name}`,
              `偏离 ${pkg.deviation_table?.items?.length ?? 0} 项，关键负偏离 ${pkg.deviation_table?.critical_negatives?.length ?? 0} 项`,
              canBid ? "✅ 可投标" : "⚠️ 存在高风险废标项",
              "右侧各章节可直接编辑，或告诉我需要修改哪部分。",
            ].join("\n"),
          }]);
        } else if (r.quote_error) {
          setTurns((ts) => [...ts, { kind: "error", text: r.quote_error! }]);
        }
      }
    } catch (e) {
      setTurns((ts) => [...ts, { kind: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally { setBusy(false); scrollBottom(); }
  }

  const handleEditorBlur = useCallback(() => {
    if (editorRef.current && doc.activeId) {
      dispatch({ type: "SET_CONTENT", id: doc.activeId, content: editorRef.current.innerText });
      dispatch({ type: "SET_STATUS",  id: doc.activeId, status: "edited" });
    }
  }, [doc.activeId]);

  async function doExport() {
    setShowExportModal(false); setBusy(true);
    try {
      const lastSpec = turns.filter((t) => t.kind === "user").at(-1)?.text ?? "";
      const blob = await downloadBidDocx(lastSpec, file);
      saveBlob(blob, "bid_package.docx");
      setTurns((ts) => [...ts, { kind: "assistant", text: "Word 文件已下载。" }]);
    } catch (e) {
      setTurns((ts) => [...ts, { kind: "error", text: e instanceof Error ? e.message : String(e) }]);
    } finally { setBusy(false); }
  }

  const hasDocs = doc.sections.some((s) => s.status !== "empty");

  return (
    <div className="chat-layout">
      {/* ── 左：对话区 ── */}
      <section className="chat-col">
        <div className="chat-scroll" ref={scrollRef}>
          {turns.length === 0 && (
            <div className="welcome">
              <h2>标书智能体</h2>
              <p className="muted">描述工况，我会生成结构化标书初稿——右侧可按章节编辑，随时追问修改。</p>
              <div className="samples">
                {SAMPLES.map((s) => <button key={s} className="sample" onClick={() => setInput(s)}>{s}</button>)}
              </div>
            </div>
          )}
          {turns.map((t, i) => {
            if (t.kind === "user")  return <div key={i} className="bubble user">{t.text}</div>;
            if (t.kind === "error") return <div key={i} className="bubble error-bubble">{t.text}</div>;
            return <div key={i} className="bubble assistant" style={{ whiteSpace: "pre-wrap" }}>{t.text}</div>;
          })}
          {busy && <div className="typing">生成中…</div>}
        </div>
        <div className="chat-input-area">
          <div className="bid-attach-bar">
            <button className="btn secondary btn-sm" onClick={() => fileRef.current?.click()} disabled={busy}>
              📎 {file ? file.name : "上传招标文件"}
            </button>
            {file && <button className="btn-clear" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; }}>×</button>}
            <input ref={fileRef} type="file" accept=".pdf,.docx,.doc,.txt,.md" style={{ display: "none" }}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </div>
          <div className="chat-input">
            <textarea value={input}
              placeholder={hasDocs ? "告诉我需要修改哪部分，例如：把技术方案的密封结构段落展开" : "描述工况，例如：球阀 DN200 PN40 蒸汽 250℃ 电动"}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
              disabled={busy} />
            <button className="btn" onClick={send} disabled={busy || !input.trim()}>发送</button>
          </div>
        </div>
      </section>

      {/* ── 右：文档编辑器 ── */}
      <section className="canvas-col bid-editor-col">
        <div className="canvas-head bid-canvas-head">
          <span>标书文档</span>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            {hasDocs && <button className="btn btn-sm" onClick={() => setShowExportModal(true)} disabled={busy}>⬇ 导出 Word</button>}
            {hasDocs && <button className="btn secondary btn-sm" onClick={() => { dispatch({ type: "RESET" }); setTurns([]); }}>重置</button>}
          </div>
        </div>
        {!hasDocs ? (
          <div className="canvas-empty">
            <p>标书文档会显示在这里</p>
            <p className="muted">生成后可按章节编辑，支持追问修改</p>
          </div>
        ) : (
          <div className="bid-editor">
            {doc.params && <ParamsBanner params={doc.params} />}
            <div className="bid-editor-body">
              <nav className="bid-outline">
                {doc.sections.map((s) => (
                  <button key={s.id}
                    className={`bid-outline-item ${doc.activeId === s.id ? "active" : ""} status-${s.status}`}
                    onClick={() => dispatch({ type: "SET_ACTIVE", id: s.id })}>
                    <span className="outline-status-dot" />
                    <span className="outline-title">{s.title}</span>
                    {s.status === "generating" && <span className="outline-spinner">⟳</span>}
                    {s.status === "edited" && <span className="outline-edited-tag">已编辑</span>}
                  </button>
                ))}
              </nav>
              <div className="bid-section-editor">
                {activeSection && (
                  <>
                    <div className="bid-section-header">
                      <h3 className="bid-section-title">{activeSection.title}</h3>
                      <div className="bid-section-actions">
                        {activeSection.status === "edited" && <span className="badge-edited">已编辑</span>}
                        {!activeSection.engineDriven && activeSection.status !== "generating" && (
                          <button className="btn secondary btn-sm"
                            onClick={() => setInput(`请重新生成「${activeSection.title}」章节，内容更详细`)}>
                            重新生成
                          </button>
                        )}
                      </div>
                    </div>
                    {activeSection.engineDriven
                      ? <EngineContent section={activeSection} />
                      : <div ref={editorRef} className="bid-content-editor"
                          contentEditable={activeSection.status !== "generating"}
                          suppressContentEditableWarning
                          onBlur={handleEditorBlur}
                          dangerouslySetInnerHTML={{ __html: mdToHtml(activeSection.content) }}
                          key={activeSection.id + activeSection.status} />
                    }
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {showExportModal && (
        <ExportModal
          sections={doc.sections} selected={exportSections}
          onToggle={(id) => setExportSections((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; })}
          onConfirm={doExport} onCancel={() => setShowExportModal(false)}
        />
      )}
    </div>
  );
}

// ─── 工具函数 ────────────────────────────────────────────────────
function detectTargetSection(msg: string): string | null {
  if (/偏离|deviation/i.test(msg)) return "deviation";
  if (/废标|废标检|风险/i.test(msg)) return "waste";
  if (/技术方案|方案|proposal/i.test(msg)) return "proposal";
  if (/质量|quality/i.test(msg)) return "quality";
  if (/业绩|案例|record/i.test(msg)) return "records";
  return null;
}

function sectionTitle(id: string): string {
  return DEFAULT_SECTIONS.find((s) => s.id === id)?.title ?? id;
}

// 极简 Markdown → HTML（只处理粗体、换行、列表）
function mdToHtml(md: string): string {
  if (!md) return "";
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>)/gs, "<ul>$1</ul>")
    .replace(/\n/g, "<br>");
}

// ─── 子组件 ──────────────────────────────────────────────────────

function ParamsBanner({ params }: { params: import("./BidDoc").BidParams }) {
  return (
    <div className={`bid-params-banner ${params.canBid ? "params-ok" : "params-fail"}`}>
      <span className="param-chip"><strong>{params.productCode}</strong> {params.productName}</span>
      {params.deviationCount > 0 && (
        <span className="param-chip">偏离 {params.deviationCount} 项</span>
      )}
      {params.criticalNegative > 0 && (
        <span className="param-chip param-danger">关键负偏离 {params.criticalNegative}</span>
      )}
      <span className={`param-verdict ${params.canBid ? "" : "param-danger"}`}>
        {params.canBid ? "✅ 可投标" : "⚠️ 高风险"}
      </span>
    </div>
  );
}

function EngineContent({ section }: { section: import("./BidDoc").DocSection }) {
  if (section.status === "empty") return <p className="muted" style={{ padding: "1rem" }}>尚未生成</p>;
  if (section.id === "deviation") return <DeviationTable content={section.content} />;
  if (section.id === "waste") return <WasteList content={section.content} />;
  return <pre className="proposal-text" style={{ padding: "0.5rem 0" }}>{section.content}</pre>;
}

function DeviationTable({ content }: { content: string }) {
  const lines = content.split("\n").filter((l) => l.startsWith("|") && !l.startsWith("| #") && !l.startsWith("|---"));
  const header = content.split("\n").find((l) => l.startsWith("| #"));
  if (!header) return <pre className="proposal-text">{content}</pre>;
  return (
    <div className="table-wrap">
      <table className="bid-table">
        <thead><tr>{header.split("|").slice(1, -1).map((h, i) => <th key={i}>{h.trim()}</th>)}</tr></thead>
        <tbody>
          {lines.map((row, i) => {
            const cells = row.split("|").slice(1, -1).map((c) => c.trim());
            const verdict = cells[4] ?? "";
            return (
              <tr key={i} className={verdict === "负偏离" && cells[1]?.includes("★") ? "row-critical" : ""}>
                {cells.map((c, j) => (
                  <td key={j} className={j === 4 ? `verdict-${c}` : ""}>{c}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function WasteList({ content }: { content: string }) {
  const blocks = content.split("\n\n").filter(Boolean);
  return (
    <div className="waste-list">
      {blocks.map((block, i) => {
        const levelMatch = block.match(/\*\[(.+?)\]\*/);
        const level = levelMatch?.[1] ?? "";
        const cls = level === "高风险" ? "fail" : level === "预警" ? "warn" : "ok";
        const text = block.replace(/\*\[.+?\]\*\s*/, "");
        const [name, ...rest] = text.split("\n");
        return (
          <div key={i} className={`waste-item waste-${cls}`}>
            <div className="waste-level">{level || "通过"}</div>
            <div className="waste-body">
              <div className="waste-name">{name}</div>
              {rest.length > 0 && <div className="waste-detail">{rest.join(" ")}</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ExportModal({
  sections,
  selected,
  onToggle,
  onConfirm,
  onCancel,
}: {
  sections: import("./BidDoc").DocSection[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="modal-overlay">
      <div className="modal-box">
        <h3 style={{ margin: "0 0 1rem" }}>选择导出章节</h3>
        <div className="modal-sections">
          {sections.map((s) => (
            <label key={s.id} className="modal-section-row">
              <input
                type="checkbox"
                checked={selected.has(s.id)}
                onChange={() => onToggle(s.id)}
                disabled={s.status === "empty"}
              />
              <span className={s.status === "empty" ? "muted" : ""}>{s.title}</span>
              <span className="muted small" style={{ marginLeft: "auto" }}>
                {s.status === "empty" ? "未生成" : s.status === "edited" ? "已编辑" : ""}
              </span>
            </label>
          ))}
        </div>
        <div className="modal-actions">
          <button className="btn" onClick={onConfirm}>下载 Word</button>
          <button className="btn secondary" onClick={onCancel}>取消</button>
        </div>
      </div>
    </div>
  );
}
