import { useEffect, useRef, useState } from "react";
import mammoth from "mammoth";
import { useSearchParams } from "react-router-dom";
import {
  createProject,
  downloadBidDocx,
  getProject,
  postTenderBid,
  postTenderParse,
  saveBlob,
  updateProject,
} from "../api/client";
import type { ProjectSave, TenderBidResponse } from "../types";
import type { BidStep, BidV3State, ContentStatus, EngineParams, OutlineNode, ParsedInfo } from "./BidV3Types";
import { initState } from "./BidV3Types";
import { BidEditor } from "./BidEditor";

// ── 步骤条 ────────────────────────────────────────────────────────
const STEPS: { key: BidStep; label: string }[] = [
  { key: "upload",  label: "上传资料" },
  { key: "parse",   label: "解析确认" },
  { key: "outline", label: "目录配置" },
  { key: "write",   label: "编写标书" },
];

function stepIndex(s: BidStep) { return STEPS.findIndex((x) => x.key === s); }

function StepBar({ current, onGo }: { current: BidStep; onGo: (s: BidStep) => void }) {
  const cur = stepIndex(current);
  return (
    <div className="v3-stepbar">
      {STEPS.map((s, i) => {
        const done = i < cur;
        const active = i === cur;
        return (
          <div key={s.key} className="v3-step-item">
            <button
              className={`v3-step-dot ${active ? "active" : done ? "done" : "pending"}`}
              onClick={() => done && onGo(s.key)}
              disabled={!done}
            >
              {done ? "✓" : i + 1}
            </button>
            <span className={`v3-step-label ${active ? "active" : done ? "done" : ""}`}>
              {s.label}
            </span>
            {i < STEPS.length - 1 && <div className={`v3-step-line ${done ? "done" : ""}`} />}
          </div>
        );
      })}
    </div>
  );
}

// ── 文档预览组件 ──────────────────────────────────────────────────
/** 把 File 渲染成 Word 样式的 HTML 预览（docx 用 mammoth，pdf 用 embed） */
function DocPreview({ file }: { file: File | null }) {
  const [html, setHtml] = useState<string | null>(null);
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!file) { setHtml(null); setObjectUrl(null); return; }
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "pdf") {
      const url = URL.createObjectURL(file);
      setObjectUrl(url);
      setHtml(null);
      return () => URL.revokeObjectURL(url);
    }
    if (ext === "docx" || ext === "doc") {
      setLoading(true);
      file.arrayBuffer().then((buf) =>
        mammoth.convertToHtml({ arrayBuffer: buf }, {
          styleMap: [
            "p[style-name='Heading 1'] => h1:fresh",
            "p[style-name='Heading 2'] => h2:fresh",
            "p[style-name='Heading 3'] => h3:fresh",
            "table => table",
          ],
        })
      ).then((result) => {
        setHtml(result.value);
        setObjectUrl(null);
      }).catch(() => setHtml("<p>文档预览失败，请检查文件格式。</p>"))
        .finally(() => setLoading(false));
    }
  }, [file]);

  if (!file) return null;
  if (loading) return <div className="v3-loading">⟳ 渲染文档…</div>;
  if (objectUrl) return (
    <embed src={objectUrl} type="application/pdf" style={{ width: "100%", height: "100%", border: "none" }} />
  );
  if (html) return (
    <div className="v3-doc-render" dangerouslySetInnerHTML={{ __html: html }} />
  );
  return <div className="v3-loading">⟳ 加载中…</div>;
}

// ── Step1：上传资料 ────────────────────────────────────────────────
function UploadZone({
  label, required, accept, file, onFile,
}: {
  label: string; required?: boolean; accept: string;
  file: File | null; onFile: (f: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  return (
    <div
      className={`v3-upload-zone ${file ? "uploaded" : ""} ${drag ? "drag" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => { e.preventDefault(); setDrag(false); const f = e.dataTransfer.files[0]; if (f) onFile(f); }}
    >
      <div className="v3-upload-label">
        <span>{label}</span>
        {required && <span className="v3-required">*必传</span>}
      </div>
      {file ? (
        <div className="v3-upload-done">
          <div className="v3-upload-check">✓</div>
          <div className="v3-upload-filename">{file.name}</div>
          <button className="v3-replace-btn" onClick={() => ref.current?.click()}>更换文件</button>
        </div>
      ) : (
        <div className="v3-upload-empty">
          <div className="v3-upload-icon">☁</div>
          <div>拖拽文件到此处，或点击上传</div>
          <div className="v3-upload-hint">支持 {accept}</div>
          <button className="btn secondary btn-sm" onClick={() => ref.current?.click()}>选择文件</button>
        </div>
      )}
      <input ref={ref} type="file" accept={accept} style={{ display: "none" }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); }} />
    </div>
  );
}

function StepUpload({
  state, setState, onNext,
}: {
  state: BidV3State;
  setState: (s: Partial<BidV3State>) => void;
  onNext: () => void;
}) {
  return (
    <div className="v3-step-body">
      <div className="v3-upload-icon-big">📄</div>
      <h2 className="v3-step-title">上传招标文件</h2>
      <p className="v3-step-desc">请上传招标文件，系统将自动解析技术需求与评分标准</p>
      <div style={{ maxWidth: 480, width: "100%" }}>
        <UploadZone
          label="招标文件" required accept=".pdf,.doc,.docx,.txt"
          file={state.tenderFile}
          onFile={(f) => setState({ tenderFile: f, projectName: f.name.replace(/\.[^.]+$/, "") })}
        />
      </div>
      <div className="v3-upload-actions">
        <button className="btn v3-primary-btn" disabled={!state.tenderFile} onClick={onNext}>
          ⚡ 自动解析招标信息 →
        </button>
      </div>
    </div>
  );
}

// ── Step2：解析确认 ────────────────────────────────────────────────

// 一级 Tab
const L1_TABS = [
  { key: "basic",  label: "基础信息" },
  { key: "qual",   label: "资格审查" },
  { key: "tech",   label: "采购需求" },
  { key: "score",  label: "评分标准" },
  { key: "waste",  label: "废标项"   },
] as const;
type L1Tab = typeof L1_TABS[number]["key"];

// 二级子 Tab 定义
const L2_TABS: Record<L1Tab, { key: string; label: string }[]> = {
  basic:  [{ key: "proj",  label: "项目信息" }, { key: "time",  label: "关键时间" }],
  qual:   [{ key: "qual",  label: "资格性审查" }, { key: "comp", label: "符合性审查" }],
  tech:   [{ key: "spec",  label: "技术规格要求" }],
  score:  [{ key: "price", label: "价格评分" }, { key: "biz",   label: "商务评分" }, { key: "tech2", label: "技术评分" }],
  waste:  [{ key: "deny",  label: "投标否决条款" }],
};

function StepParse({
  state, onNext, loading,
}: {
  state: BidV3State;
  onNext: () => void;
  loading: boolean;
}) {
  const [l1, setL1] = useState<L1Tab>("basic");
  const [l2, setL2] = useState<string>("proj");
  const info = state.parsedInfo;

  // 切换 L1 时同步 L2 默认
  function switchL1(key: L1Tab) {
    setL1(key);
    setL2(L2_TABS[key][0].key);
  }

  return (
    <div className="v3-parse2-layout">
      {/* 左：文档预览 */}
      <div className="v3-parse2-doc">
        <div className="v3-panel-head">
          招标文件
          {state.projectName && <span className="v3-project-name">{state.projectName}</span>}
        </div>
        <div className="v3-rawtext-scroll">
          {loading && !state.tenderFile ? (
            <div className="v3-loading">⟳ 正在解析招标文件…</div>
          ) : state.tenderFile ? (
            <DocPreview file={state.tenderFile} />
          ) : (
            <div className="v3-panel-empty">未上传招标文件</div>
          )}
        </div>
      </div>

      {/* 右：解析结果 */}
      <aside className="v3-parse2-result">
        <div className="v3-parse2-head">
          <span className="v3-parse2-title">招标关键信息</span>
          {info && (
            <button className="btn btn-sm v3-primary-btn" onClick={onNext} disabled={loading}>
              生成目录 →
            </button>
          )}
        </div>

        {/* L1 Tab */}
        <div className="v3-l1-tabs">
          {L1_TABS.map((t) => (
            <button key={t.key}
              className={`v3-l1-tab ${l1 === t.key ? "active" : ""}`}
              onClick={() => switchL1(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {/* L2 Sub-tab */}
        <div className="v3-l2-tabs">
          {L2_TABS[l1].map((t) => (
            <button key={t.key}
              className={`v3-l2-tab ${l2 === t.key ? "active" : ""}`}
              onClick={() => setL2(t.key)}>
              {t.label}
            </button>
          ))}
        </div>

        {/* 内容区 */}
        <div className="v3-parse2-body">
          {!info ? (
            <div className="v3-panel-empty">{loading ? "⟳ 解析中…" : "请先上传招标文件"}</div>
          ) : (
            <ParseContent l1={l1} l2={l2} info={info} />
          )}
        </div>
      </aside>
    </div>
  );
}

// ── 解析内容渲染 ──────────────────────────────────────────────────
function InfoTable({ rows }: { rows: [string, string][] }) {
  return (
    <div className="v3-result-section">
      <table className="v3-result-table">
        <thead><tr><th>标题</th><th>内容</th></tr></thead>
        <tbody>
          {rows.filter(([, v]) => v).map(([k, v], i) => (
            <tr key={i}><td>{k}</td><td>{v}</td></tr>
          ))}
          {rows.every(([, v]) => !v) && (
            <tr><td colSpan={2} className="muted small" style={{ padding: "1rem" }}>暂无信息</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function SectionTable({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="v3-result-section">
      <div className="v3-result-section-title">{title}</div>
      <table className="v3-result-table">
        <thead><tr><th>标题</th><th>内容</th></tr></thead>
        <tbody>
          {rows.map(([k, v], i) => (
            <tr key={i}><td>{k}</td><td>{v || "—"}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ParseContent({ l1, l2, info }: { l1: L1Tab; l2: string; info: ParsedInfo }) {
  // 基础信息
  if (l1 === "basic" && l2 === "proj") return (
    <InfoTable rows={[
      ["项目名称", info.projectName],
      ["招标编号", info.projectNo],
      ["招标人",   info.owner],
      ["代理机构", info.agency],
      ["预算金额", info.budget],
      ["保证金",   info.bondInfo],
    ]} />
  );
  if (l1 === "basic" && l2 === "time") return (
    <div className="v3-result-section">
      <table className="v3-result-table">
        <thead><tr><th>事项</th><th>时间</th></tr></thead>
        <tbody>
          {info.keyDates.length ? info.keyDates.map((d, i) => (
            <tr key={i}><td>{d.name}</td><td>{d.time || "—"}</td></tr>
          )) : <tr><td colSpan={2} className="muted small" style={{ padding: "1rem" }}>暂无时间节点</td></tr>}
          {info.deadline && <tr><td>投标截止时间</td><td>{info.deadline}</td></tr>}
        </tbody>
      </table>
    </div>
  );

  // 资格审查
  if (l1 === "qual" && l2 === "qual") return (
    <SectionTable title="资格性审查" rows={[
      ["营业执照",  "在有效期内，经营范围含工业阀门制造或销售"],
      ["资质要求",  info.qualifications.join("、") || "—"],
      ["财务状况",  "近两年财务报表，资产负债率 ≤ 75%，无重大违约记录"],
      ["业绩要求",  `近三年同类业绩不少于 3 项，单项合同额 ≥ 50 万元`],
      ["信誉要求",  "无重大违约记录；无串通投标或弄虚作假行为"],
      ["售后服务",  "在项目所在省份设有售后服务机构或签约授权服务商"],
    ]} />
  );
  if (l1 === "qual" && l2 === "comp") return (
    <SectionTable title="符合性审查" rows={[
      ["投标文件密封", "投标文件须按规定密封，密封符合要求"],
      ["签字盖章",     "投标函、法人授权、报价表等均已签字并加盖公章"],
      ["保证金",       "投标保证金须在规定时间内到达指定账户"],
    ]} />
  );

  // 采购需求
  if (l1 === "tech") return (
    <div className="v3-result-section">
      <div className="v3-result-section-title">技术规格要求</div>
      <table className="v3-result-table">
        <thead><tr><th>参数</th><th>要求</th><th></th></tr></thead>
        <tbody>
          {info.techRequirements.length ? info.techRequirements.map((r, i) => (
            <tr key={i} className={r.critical ? "row-critical" : ""}>
              <td>{r.param}</td>
              <td>{r.value}</td>
              <td>{r.critical ? <span className="v3-critical-tag">关键</span> : ""}</td>
            </tr>
          )) : <tr><td colSpan={3} className="muted small" style={{ padding: "1rem" }}>暂无技术参数</td></tr>}
        </tbody>
      </table>
    </div>
  );

  // 评分标准（分三类展示）
  if (l1 === "score") {
    // 按评分类别分组
    const priceItems = info.scoringItems.filter(s => /价格|报价|商务/.test(s.name));
    const bizItems   = info.scoringItems.filter(s => /质量|业绩|资质/.test(s.name));
    const techItems  = info.scoringItems.filter(s => /技术|方案|服务/.test(s.name));
    const groupMap: Record<string, typeof info.scoringItems> = {
      price: priceItems.length ? priceItems : info.scoringItems.filter((_, i) => i === 2),
      biz:   bizItems.length   ? bizItems   : info.scoringItems.filter((_, i) => i === 1),
      tech2: techItems.length  ? techItems  : info.scoringItems.filter((_, i) => i === 0 || i === 3),
    };
    const items = groupMap[l2] ?? info.scoringItems;
    const sectionTitle = L2_TABS.score.find(t => t.key === l2)?.label ?? "评分";
    return (
      <div className="v3-result-section">
        <div className="v3-result-section-title">{sectionTitle}</div>
        <table className="v3-result-table">
          <thead><tr><th>评分项目</th><th>分值</th><th>评分说明</th></tr></thead>
          <tbody>
            {items.length ? items.map((s, i) => (
              <tr key={i}>
                <td>{s.name}</td>
                <td><strong style={{ color: "var(--accent)" }}>{s.score}</strong></td>
                <td className="small">{s.desc}</td>
              </tr>
            )) : <tr><td colSpan={3} className="muted small" style={{ padding: "1rem" }}>暂无数据</td></tr>}
          </tbody>
        </table>
      </div>
    );
  }

  // 废标项
  if (l1 === "waste") return (
    <div className="v3-result-section">
      <div className="v3-result-section-title">投标否决条款</div>
      <table className="v3-result-table">
        <thead><tr><th>标题</th><th>内容</th></tr></thead>
        <tbody>
          {info.wasteItems.length ? info.wasteItems.map((w, i) => {
            // 把 "1. xxx" 拆成条目
            const m = w.match(/^[\d]+[.、]\s*(.+)/);
            const content = m ? m[1] : w;
            const labels = ["密封要求","保证金要求","资质要求","技术偏离","报价异常","重复投标","递交时间","违规行为"];
            return (
              <tr key={i}><td>{labels[i] ?? `条款 ${i+1}`}</td><td>{content}</td></tr>
            );
          }) : <tr><td colSpan={2} className="muted small" style={{ padding: "1rem" }}>暂无废标条款</td></tr>}
        </tbody>
      </table>
    </div>
  );

  return null;
}

// ── Step3：目录配置 ────────────────────────────────────────────────
function StepOutline({
  state, setState, onNext, loading,
}: {
  state: BidV3State;
  setState: (s: Partial<BidV3State>) => void;
  onNext: () => void;
  loading?: boolean;
}) {
  const outline = state.outline;
  const totalWords = outline.reduce((s, n) => s + n.wordHint, 0);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");

  function move(idx: number, dir: -1 | 1) {
    const arr = [...outline];
    const to = idx + dir;
    if (to < 0 || to >= arr.length) return;
    [arr[idx], arr[to]] = [arr[to], arr[idx]];
    setState({ outline: arr });
  }

  function remove(id: string) {
    setState({ outline: outline.filter((n) => n.id !== id) });
  }

  function startEdit(n: OutlineNode) {
    if (n.engineLocked) return;
    setEditingId(n.id);
    setEditVal(n.title);
  }

  function commitEdit(id: string) {
    if (!editVal.trim()) { setEditingId(null); return; }
    setState({ outline: outline.map((n) => n.id === id ? { ...n, title: editVal } : n) });
    setEditingId(null);
  }

  function addNode() {
    const newNode: OutlineNode = {
      id: `custom-${Date.now()}`,
      title: "新章节",
      level: 1,
      engineLocked: false,
      wordHint: 500,
      status: "empty",
      content: "",
    };
    setState({ outline: [...outline, newNode] });
  }

  // 一级章节的序号（只计 level=1）
  let h1Count = 0;

  return (
    <div className="v3-outline2-layout">
      {/* 左：文档预览 */}
      <div className="v3-outline2-doc">
        <div className="v3-panel-head">
          招标文件
          {state.projectName && <span className="v3-project-name">{state.projectName}</span>}
        </div>
        <div className="v3-rawtext-scroll">
          {state.tenderFile
            ? <DocPreview file={state.tenderFile} />
            : <div className="v3-panel-empty">未上传招标文件</div>}
        </div>
      </div>

      {/* 右：目录配置 */}
      <div className="v3-outline2-right">
        {/* 顶栏 */}
        <div className="v3-outline2-toolbar">
          <span className="v3-outline-toolbar-title">编写目录</span>
          <button className="v3-add-section-btn" onClick={addNode}>
            <span>+</span> 新增章节
          </button>
        </div>

        {/* 目录树 */}
        <div className="v3-outline-tree">
          {outline.map((n, i) => {
            if (n.level === 1) h1Count++;
            const seqLabel = n.level === 1 ? `${h1Count}` : "—";
            return (
              <div key={n.id} className={`v3-ol-row ${n.level === 2 ? "sub" : ""}`}>
                <span className={`v3-ol-seq ${n.level === 1 ? "h1" : "h2"}`}>{seqLabel}</span>
                <div className="v3-ol-title-wrap" onDoubleClick={() => startEdit(n)}>
                  {editingId === n.id ? (
                    <input className="v3-ol-input" value={editVal}
                      onChange={(e) => setEditVal(e.target.value)}
                      onBlur={() => commitEdit(n.id)}
                      onKeyDown={(e) => { if (e.key === "Enter") commitEdit(n.id); if (e.key === "Escape") setEditingId(null); }}
                      autoFocus />
                  ) : (
                    <span className="v3-ol-title">{n.title}</span>
                  )}
                  {n.engineLocked && <span className="v3-ol-lock" title="引擎确定性生成">🔒</span>}
                </div>
                <span className="v3-ol-words">{n.wordHint.toLocaleString()} 字</span>
                <div className="v3-ol-actions">
                  <button className="v3-ol-btn" onClick={() => move(i, -1)} disabled={i === 0} title="上移">↑</button>
                  <button className="v3-ol-btn" onClick={() => move(i, 1)} disabled={i === outline.length - 1} title="下移">↓</button>
                  <button className="v3-ol-btn del" onClick={() => !n.engineLocked && remove(n.id)}
                    disabled={n.engineLocked} title={n.engineLocked ? "引擎锁定" : "删除"}>✕</button>
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部 */}
        <div className="v3-outline-footer">
          <span className="v3-ol-total">
            共 <strong>{outline.length}</strong> 章节 · 预估总字数 <strong>{totalWords.toLocaleString()}</strong> 字
          </span>
          <button className="btn v3-primary-btn" onClick={onNext} disabled={loading}>
            {loading ? "⟳ 生成中…" : "开始编写 →"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Step4 子组件：引擎锁定章节渲染 ────────────────────────────────
function EngineSection({ node }: { node: OutlineNode }) {
  const { id, content } = node;
  if (id === "dev-table" || id === "dev-params") {
    // 简单 Markdown 表格解析
    const rows = content.split("\n").filter((l) => l.trim().startsWith("|"));
    return (
      <div className="v3-engine-table-wrap">
        <table className="v3-engine-table">
          <tbody>
            {rows.map((row, ri) => {
              const cells = row.split("|").filter((_, ci) => ci > 0 && ci < row.split("|").length - 1);
              if (cells.every((c) => /^[-: ]+$/.test(c))) return null;
              return (
                <tr key={ri}>
                  {cells.map((c, ci) =>
                    ri === 0
                      ? <th key={ci}>{c.trim()}</th>
                      : <td key={ci}>{c.trim()}</td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
  if (id === "waste-check") {
    const paras = content.split(/\n\n+/).filter(Boolean);
    return (
      <div className="v3-waste-cards">
        {paras.map((p, i) => (
          <div key={i} className="v3-waste-card">{p}</div>
        ))}
      </div>
    );
  }
  if (id === "records") {
    const items = content.split("\n").filter(Boolean);
    return (
      <ul className="v3-records-list">
        {items.map((item, i) => <li key={i}>{item.replace(/^[-•*]\s*/, "")}</li>)}
      </ul>
    );
  }
  return <pre className="v3-engine-pre">{content || "（暂无内容）"}</pre>;
}

// 极简 Markdown → HTML（粗体、换行、列表）
function mdToHtml(md: string): string {
  if (!md) return "";
  return md
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/^[-•] (.+)$/gm, "<li>$1</li>")
    .replace(/\n/g, "<br>");
}

// ── Step4：编写标书 ────────────────────────────────────────────────
function StepWrite({
  state, setState, setStateRaw, onExport, exporting,
}: {
  state: BidV3State;
  setState: (s: Partial<BidV3State>) => void;
  setStateRaw: (updater: (prev: BidV3State) => BidV3State) => void;
  onExport: () => void;
  exporting: boolean;
}) {
  const { outline, engineParams } = state;
  const [chatInput, setChatInput] = useState("");
  const [chatMsgs, setChatMsgs] = useState<{ role: "user" | "ai"; text: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [activeId, setActiveId] = useState(outline[0]?.id ?? "");
  const docScrollRef = useRef<HTMLDivElement>(null);
  const sectionRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // 总字数
  const totalWords = outline.reduce((s, n) => s + (n.content?.length ?? 0), 0);
  const doneCount = outline.filter((n) => n.status !== "empty").length;

  // 进入编写页时，逐章为空章节生成内容（按章节标题差异化生成）
  useEffect(() => {
    const emptyLLM = outline.filter((n) => !n.engineLocked && n.status === "empty");
    if (emptyLLM.length === 0) return;
    // 逐章串行生成，避免并发打满
    (async () => {
      for (const node of emptyLLM) {
        setState({
          outline: outline.map((n) =>
            n.id === node.id ? { ...n, status: "generating" as ContentStatus } : n
          ),
        });
        try {
          const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: `请为标书撰写「${node.title}」章节，针对产品 ${engineParams?.productCode ?? "阀门"}，专业、简洁、符合投标要求，约 ${node.wordHint} 字。`,
            }),
          });
          const data = await res.json();
          const text: string = data.text ?? data.message ?? data.content ?? "";
          setStateRaw((prev) => ({
            ...prev,
            outline: prev.outline.map((n) =>
              n.id === node.id
                ? { ...n, content: text, status: "done" as ContentStatus }
                : n
            ),
          }));
        } catch {
          setStateRaw((prev) => ({
            ...prev,
            outline: prev.outline.map((n) =>
              n.id === node.id ? { ...n, status: "empty" as ContentStatus } : n
            ),
          }));
        }
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 点击大纲滚动到对应章节
  function scrollToSection(id: string) {
    setActiveId(id);
    const el = sectionRefs.current[id];
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // IntersectionObserver 更新活跃章节
  useEffect(() => {
    const container = docScrollRef.current;
    if (!container) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActiveId(e.target.id.replace("sec-", ""));
        }
      },
      { root: container, threshold: 0.3 },
    );
    Object.values(sectionRefs.current).forEach((el) => el && observer.observe(el));
    return () => observer.disconnect();
  }, [outline.length]);

  function updateContent(id: string, val: string) {
    setStateRaw((prev) => ({
      ...prev,
      outline: prev.outline.map((n) =>
        n.id === id ? { ...n, content: val, status: "edited" as ContentStatus } : n
      ),
    }));
  }

  async function sendChat() {
    const msg = chatInput.trim();
    const activeNode = outline.find((n) => n.id === activeId);
    if (!msg || !activeNode) return;
    setChatMsgs((m) => [...m, { role: "user", text: msg }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: `针对章节「${activeNode.title}」：${msg}` }),
      });
      const data = await res.json();
      const reply: string = data.text ?? data.message ?? data.content ?? "（暂无回复）";
      setChatMsgs((m) => [...m, { role: "ai", text: reply }]);
      setStateRaw((prev) => ({
        ...prev,
        outline: prev.outline.map((n) =>
          n.id === activeNode.id
            ? { ...n, content: (n.content ? n.content + "\n\n" : "") + reply, status: "edited" as ContentStatus }
            : n
        ),
      }));
    } catch {
      setChatMsgs((m) => [...m, { role: "ai", text: "请求失败，请重试。" }]);
    } finally {
      setChatLoading(false);
    }
  }

  const activeNodeTitle = outline.find((n) => n.id === activeId)?.title ?? "";

  return (
    <div className="v3-write-layout">
      {/* ── 左：章节导航 ── */}
      <nav className="v3-write-outline">
        <div className="v3-write-outline-head">章节大纲</div>
        <div className="v3-write-nav">
          {outline.map((n) => (
            <div key={n.id}
              className={`v3-nav-item level-${n.level} st-${n.status} ${n.id === activeId ? "active" : ""}`}
              onClick={() => scrollToSection(n.id)}
            >
              <span className="v3-nav-dot" />
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {n.title}
              </span>
              {n.status === "generating" && <span style={{ fontSize: "0.65rem", color: "var(--accent)" }}>⟳</span>}
              {n.engineLocked && <span className="v3-nav-lock">🔒</span>}
            </div>
          ))}
        </div>
        {/* 进度 */}
        <div className="v3-write-nav-footer">
          {doneCount}/{outline.length} 章 · {totalWords.toLocaleString()} 字
        </div>
      </nav>

      {/* ── 中：全文连续文档区 ── */}
      <div className="v3-write-body" ref={docScrollRef}>
        <div className="v3-full-doc">
          {outline.map((n) => (
            <div
              key={n.id}
              id={`sec-${n.id}`}
              ref={(el) => { sectionRefs.current[n.id] = el; }}
              className={`v3-full-section level-${n.level}`}
            >
              {/* 章节标题行 */}
              <div className="v3-full-section-head">
                <h3 className={`v3-full-h ${n.level === 1 ? "h1" : "h2"}`}>{n.title}</h3>
                <div className="v3-full-section-actions">
                  {n.status === "generating" && <span className="v3-gen-badge">生成中…</span>}
                  {n.status === "done" && <span className="v3-done-badge">已完成</span>}
                  {n.status === "edited" && <span className="v3-edited-badge">已编辑</span>}
                  {!n.engineLocked && n.status !== "generating" && (
                    <button className="v3-regen-btn" onClick={() => {
                      setChatInput(`请重新生成「${n.title}」章节，内容更充实`);
                      scrollToSection(n.id);
                    }}>↺ 重写</button>
                  )}
                </div>
              </div>

              {/* 章节内容 */}
              <div className="v3-full-section-body">
                {n.status === "generating" ? (
                  <div className="v3-section-loading">⟳ 正在生成「{n.title}」…</div>
                ) : n.status === "empty" && !n.engineLocked ? (
                  <div className="v3-section-empty">
                    此章节内容为空，在右侧 AI 助手中输入指令生成。
                  </div>
                ) : n.engineLocked ? (
                  <EngineSection node={n} />
                ) : (
                  <div
                    className="v3-doc-editable"
                    contentEditable
                    suppressContentEditableWarning
                    onBlur={(e) => updateContent(n.id, e.currentTarget.innerText ?? "")}
                    dangerouslySetInnerHTML={{ __html: mdToHtml(n.content) }}
                    key={n.id + n.status}
                  />
                )}
              </div>
            </div>
          ))}
          <div style={{ height: "4rem" }} />
        </div>
      </div>

      {/* ── 右：AI 助手面板 ── */}
      <aside className="v3-write-panel">
        {engineParams && (
          <div className="v3-panel-section">
            <div className="v3-panel-section-title">关键参数</div>
            <div className="v3-params-card">
              <div className="v3-params-row"><span className="v3-params-key">型号</span><span>{engineParams.productCode}</span></div>
              <div className="v3-params-row"><span className="v3-params-key">偏离数</span><span>{engineParams.deviationCount} 项</span></div>
              <div className="v3-params-row">
                <span className="v3-params-key">投标</span>
                <span className={`v3-params-verdict ${engineParams.canBid ? "ok" : "fail"}`}>
                  {engineParams.canBid ? "✅ 可投标" : "⚠️ 高风险"}
                </span>
              </div>
            </div>
          </div>
        )}
        <div className="v3-ai-chat">
          <div className="v3-ai-title">AI 助手</div>
          <div className="v3-ai-msgs">
            {chatMsgs.length === 0 && (
              <p className="muted small" style={{ padding: "0.25rem 0" }}>针对当前章节追问或修改</p>
            )}
            {chatMsgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "v3-ai-msg-user" : "v3-ai-msg-ai"}>{m.text}</div>
            ))}
            {chatLoading && <div className="muted small">AI 思考中…</div>}
          </div>
          <div className="v3-ai-input">
            <textarea
              value={chatInput}
              placeholder={`针对「${activeNodeTitle || "当前章节"}」提问…`}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } }}
              disabled={chatLoading}
            />
            <button className="btn v3-ai-send" onClick={sendChat} disabled={chatLoading || !chatInput.trim()}>发送</button>
          </div>
        </div>
        <div style={{ padding: "0.75rem", borderTop: "1px solid var(--border)" }}>
          <button className="btn v3-primary-btn" style={{ width: "100%" }} onClick={onExport} disabled={exporting}>
            {exporting ? "导出中…" : "⬇ 导出 Word"}
          </button>
        </div>
      </aside>
    </div>
  );
}

/** 已消耗字数 = 各章节内容长度之和。 */
function wordCount(outline: OutlineNode[]): number {
  return outline.reduce((s, n) => s + (n.content?.length ?? 0), 0);
}

/** 组装续编所需的整份快照(不含 File,无法序列化)。 */
function buildSnapshot(s: BidV3State, outline: OutlineNode[], engineParams: EngineParams | null) {
  return {
    step: "write" as BidStep,
    projectName: s.projectName,
    parsedInfo: s.parsedInfo,
    rawText: s.rawText,
    outline,
    activeNodeId: s.activeNodeId,
    engineParams,
  };
}

// ── 主组件 ────────────────────────────────────────────────────────
export function BidPageV3() {
  const [searchParams] = useSearchParams();
  const [state, setStateRaw] = useState<BidV3State>(initState);
  const [parsing, setParsing] = useState(false);
  const [outlineLoading, setOutlineLoading] = useState(false);
  const [exporting, setExporting] = useState(false);

  function setState(patch: Partial<BidV3State>) {
    setStateRaw((s) => ({ ...s, ...patch }));
  }

  // 带 ?pid 进入:从后端水合记录,直接跳到「编写标书」续编
  useEffect(() => {
    const pid = searchParams.get("pid");
    if (!pid) return;
    (async () => {
      try {
        const proj = await getProject(pid);
        const snap = proj.snapshot as Partial<BidV3State>;
        setStateRaw((s) => ({
          ...s,
          ...snap,
          projectId: proj.id,
          projectName: proj.project_name || snap.projectName || s.projectName,
          tenderFile: null,
          boqFile: null,
          step: "write",
        }));
      } catch (e) {
        console.error("加载项目失败", e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  async function goToParse() {
    if (!state.tenderFile) {
      setState({ step: "parse" });
      return;
    }
    setParsing(true);
    setState({ step: "parse" });
    try {
      const parsed = await postTenderParse(state.tenderFile);

      // 从 risks 中分离评分项（level=评分）
      const scoringRisks = parsed.brief.risks.filter((r) => r.level === "评分");
      const scoringItems = scoringRisks.length > 0
        ? scoringRisks.map((r) => {
            const m = r.summary.match(/(.+?)（(\d+)分）/);
            return {
              name: m ? m[1].trim() : r.summary.slice(0, 16),
              score: m ? parseInt(m[2]) : 25,
              desc: r.clause.split("|").slice(2).join("").trim() || r.clause,
            };
          })
        : [
            { name: "技术方案与参数响应", score: 40, desc: "技术偏离表；关键参数逐一对比" },
            { name: "产品质量与业绩",     score: 25, desc: "第三方检测报告；近三年业绩" },
            { name: "商务报价",           score: 25, desc: "综合评分，偏差最小得满分" },
            { name: "售后服务能力",       score: 10, desc: "服务响应时间；备件供应承诺" },
          ];

      // 技术需求：去重，优先展示大值（最高要求）
      const techMap = new Map<string, typeof parsed.requirements[0]>();
      for (const r of parsed.requirements) {
        const existing = techMap.get(r.param);
        if (!existing || (r.target_value ?? 0) > (existing.target_value ?? 0)) {
          techMap.set(r.param, r);
        }
      }

      const info: ParsedInfo = {
        projectName: parsed.brief.title,
        projectNo: "",
        deadline: parsed.brief.bid_deadline ?? "",
        owner: "",
        agency: "",
        budget: "",
        qualifications: parsed.brief.required_qual_categories,
        techRequirements: Array.from(techMap.values()).map((r) => ({
          param: r.param,
          value: r.target_value != null
            ? `${r.op === ">=" ? "≥" : r.op} ${r.target_value} ${r.unit}`.trim()
            : (r.target_set?.join(" / ") ?? r.raw),
          critical: r.is_critical,
        })),
        wasteItems: parsed.waste_clauses,
        scoringItems,
        keyDates: parsed.brief.key_points.map((p) => ({ name: p, time: "" })),
        bondInfo: "",
      };

      setState({
        parsedInfo: info,
        projectName: info.projectName || state.projectName,
        // 使用完整原文
        rawText: parsed.raw_text ?? parsed.brief.key_points.join("\n") + "\n\n" + parsed.waste_clauses.join("\n"),
      });
    } catch (e) {
      console.error("解析失败", e);
    } finally {
      setParsing(false);
    }
  }

  async function goToOutline() {
    const { parsedInfo, tenderFile } = state;
    setState({ step: "outline" });
    setOutlineLoading(true);

    // 从技术需求构造自然语言 spec（供 ConditionParser 解析）
    const reqs = parsedInfo?.techRequirements ?? [];
    const raw = state.rawText ?? "";

    // 从原文直接提取第一个 DN/PN/温度（最可靠，不依赖解析器的要求值）
    const rawDnMatch = raw.match(/DN\s*(\d+)/g);
    const rawPnMatch = raw.match(/PN\s*(\d+(?:\.\d+)?)/g);
    const rawTempMatch = raw.match(/(\d{2,3})\s*℃/g);

    // 从所有 DN 里取 ≤250 的最大值
    const allDns = (rawDnMatch ?? []).map(s => parseInt(s.replace(/DN\s*/, ""))).filter(v => !isNaN(v));
    const validDns = allDns.filter(v => v <= 250);
    const dn = validDns.length > 0 ? Math.max(...validDns) : 200;

    // 最高 PN 要求
    const allPns = (rawPnMatch ?? []).map(s => parseFloat(s.replace(/PN\s*/, ""))).filter(v => !isNaN(v));
    const pn = allPns.length > 0 ? Math.max(...allPns) : 16;

    // 最高温度要求
    const allTemps = (rawTempMatch ?? []).map(s => parseInt(s)).filter(v => !isNaN(v));
    const temp = allTemps.length > 0 ? Math.max(...allTemps) : undefined;

    const driveReq = reqs.find((r) => r.param === "驱动方式");
    const stdReq = reqs.find((r) => r.param === "执行标准");
    const matReq = reqs.find((r) => r.param === "阀体材质");
    const drive = driveReq?.value ?? "";
    const std = stdReq?.value ?? "";
    const mat = matReq?.value ?? "";

    let medium = "水";
    if (raw.includes("蒸汽")) medium = "蒸汽";
    else if (raw.includes("化工")) medium = "化工介质";
    else if (raw.includes("油")) medium = "油品";

    // 找阀门类型
    let valveType = "阀门";
    if (raw.includes("球阀")) valveType = "球阀";
    else if (raw.includes("蝶阀")) valveType = "蝶阀";
    else if (raw.includes("截止阀")) valveType = "截止阀";
    else if (raw.includes("闸阀")) valveType = "闸阀";

    const specParts = [
      valveType,
      `DN${dn}`,
      `PN${pn}`,
      medium,
      temp ? `${temp}℃` : "",
      drive,
      std,
      mat,
    ].filter(Boolean);
    const spec = specParts.join(" ");

    try {
      const resp: TenderBidResponse = await postTenderBid(spec, tenderFile);
      const pkg = resp.package;
      if (!pkg) {
        console.warn("goToOutline: pkg 为空，spec=", spec);
        return;
      }
      const ep: EngineParams = {
        productCode: pkg.product_code,
        productName: pkg.product_name,
        deviationCount: pkg.deviation_table?.items?.length ?? 0,
        criticalNeg: pkg.deviation_table?.critical_negatives?.length ?? 0,
        canBid: pkg.can_bid ?? !(pkg.compliance_report?.items ?? []).some((i) => i.level === "高风险"),
      };
      const devTableMd = [
        "| 序号 | 参数 | 招标要求 | 产品能力 | 判定 |",
        "|---|---|---|---|---|",
        ...(pkg.deviation_table?.items ?? []).map((d) =>
          `| ${d.seq} | ${d.param}${d.is_critical ? " ★" : ""} | ${d.requirement} | ${d.product_capability} | ${d.verdict} |`
        ),
      ].join("\n");
      const wasteContent = (pkg.compliance_report?.items ?? []).map((c) =>
        `【${c.level}】${c.name}\n${c.detail}`
      ).join("\n\n");
      // 业绩内容从 tech_proposal 里提取，或用 RAG 结果
      const recordsContent = (pkg as any).matched_records
        ? (pkg as any).matched_records.slice(0, 5).map((r: any) =>
            `- ${r.project_name}（${r.customer}，${r.valve_type}，${r.contract_date}，约${(r.amount/1e4).toFixed(0)}万元）`
          ).join("\n")
        : "";
      const proposalContent = pkg.tech_proposal ?? "";

      // 把所有更新合并为一次 setState，彻底消除竞争
      setStateRaw((prev) => ({
        ...prev,
        engineParams: ep,
        outline: prev.outline.map((n) => {
          if (n.id === "dev-table" || n.id === "dev-params")
            return { ...n, content: devTableMd, status: "done" as ContentStatus };
          if (n.id === "waste-check")
            return { ...n, content: wasteContent, status: "done" as ContentStatus };
          if (n.id === "records")
            return { ...n, content: recordsContent, status: (recordsContent ? "done" : "empty") as ContentStatus };
          if (!n.engineLocked && proposalContent)
            return { ...n, content: proposalContent, status: "done" as ContentStatus };
          return n;
        }),
      }));
      console.log("[goToOutline] setStateRaw done, proposalContent len=", proposalContent.length);
      // persistProject 暂时跳过（newOutline 变量已移除）
    } catch (e) {
      console.error("标书生成失败", e);
    } finally {
      setOutlineLoading(false);
    }
  }

  /** 创建或更新项目记录。内容生成后首次调用创建,之后编辑/导出更新同一条。 */
  async function persistProject(s: BidV3State, spec: string): Promise<void> {
    const payload: ProjectSave = {
      project_name: s.projectName || "未命名标书",
      word_count: wordCount(s.outline),
      spec,
      status: "completed",
      snapshot: buildSnapshot(s, s.outline, s.engineParams),
    };
    try {
      if (s.projectId) {
        await updateProject(s.projectId, payload);
      } else {
        const created = await createProject(payload);
        setState({ projectId: created.id });
      }
    } catch (e) {
      console.error("保存项目记录失败", e);
    }
  }

  function goToWrite() {
    const hasContent = state.outline.some(n => n.content);
    if (!hasContent && !outlineLoading) {
      goToOutline().then(() => {
        setState({ step: "write" });
        triggerGenerate();
      });
    } else {
      setState({ step: "write" });
      triggerGenerate();
    }
  }

  // 逐章为空的 LLM 章节生成内容
  function triggerGenerate() {
    const emptyLLM = state.outline.filter((n) => !n.engineLocked && n.status === "empty");
    if (emptyLLM.length === 0) return;
    const engineCode = state.engineParams?.productCode ?? "阀门";
    (async () => {
      for (const node of emptyLLM) {
        setStateRaw((prev) => ({
          ...prev,
          outline: prev.outline.map((n) =>
            n.id === node.id ? { ...n, status: "generating" as ContentStatus } : n
          ),
        }));
        try {
          const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: `请为投标标书撰写「${node.title}」章节，产品为 ${engineCode}，专业简洁，约 ${node.wordHint} 字。`,
            }),
          });
          const data = await res.json();
          const text: string = data.text ?? data.message ?? data.content ?? "";
          setStateRaw((prev) => ({
            ...prev,
            outline: prev.outline.map((n) =>
              n.id === node.id ? { ...n, content: text, status: "done" as ContentStatus } : n
            ),
          }));
        } catch {
          setStateRaw((prev) => ({
            ...prev,
            outline: prev.outline.map((n) =>
              n.id === node.id ? { ...n, status: "empty" as ContentStatus } : n
            ),
          }));
        }
      }
    })();
  }

  async function doExport() {
    setExporting(true);
    try {
      const spec = state.parsedInfo?.techRequirements.slice(0, 3)
        .map((r) => `${r.param} ${r.value}`).join("，") ?? "阀门";
      const blob = await downloadBidDocx(spec, state.tenderFile);
      saveBlob(blob, `${state.projectName || "标书"}.docx`);
      // 导出前把最新编辑落盘到项目记录
      if (state.projectId) void persistProject(state, spec);
    } catch (e) {
      console.error("导出失败", e);
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="v3-root">
      <div className="v3-header">
        <span className="v3-back" onClick={() => setState({ step: "upload" })}>← 返回</span>
        {state.projectName && (
          <span className="v3-project-title">{state.projectName}</span>
        )}
        <StepBar current={state.step} onGo={(s) => {
          if (s === "write" && state.outline.every(n => !n.content)) return; // 内容未生成禁止直跳
          setState({ step: s });
        }} />
        {state.step === "write" && (
          <button className="btn btn-sm" onClick={doExport} disabled={exporting}>
            ⬇ 导出 Word
          </button>
        )}
        {parsing && <span className="v3-parsing-badge">⟳ 解析中…</span>}
      </div>
      <div className="v3-body">
        {state.step === "upload" && (
          <StepUpload state={state} setState={setState} onNext={goToParse} />
        )}
        {state.step === "parse" && (
          <StepParse state={state} onNext={goToOutline} loading={parsing} />
        )}
        {state.step === "outline" && (
          <StepOutline state={state} setState={setState} onNext={goToWrite} loading={outlineLoading} />
        )}
        {state.step === "write" && (
          <BidEditor state={state} setStateRaw={setStateRaw} onExport={doExport} exporting={exporting} />
        )}
      </div>
    </div>
  );
}

