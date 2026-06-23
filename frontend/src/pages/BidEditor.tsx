/**
 * BidEditor — Tiptap 驱动的标书全文编辑器
 *
 * 布局：
 *  - 左侧大纲导航（IntersectionObserver 驱动活跃章节高亮）
 *  - 中间 A4 白纸文档（单张连续，章节间用 h2 分隔）
 *  - 右侧 AI 助手面板
 *
 * 只读区域（引擎锁定章节）通过 Tiptap NodeView 的 contenteditable=false 实现。
 */

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Table } from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableHeader from "@tiptap/extension-table-header";
import TableCell from "@tiptap/extension-table-cell";
import { useEffect, useRef, useState } from "react";
import type { BidV3State, ContentStatus, OutlineNode } from "./BidV3Types";

interface BidEditorProps {
  state: BidV3State;
  setStateRaw: (updater: (prev: BidV3State) => BidV3State) => void;
  onExport: () => void;
  exporting: boolean;
}

// ── 把 outline 数组转成 Tiptap 的 JSON 文档 ──────────────────────
function outlineToDoc(outline: OutlineNode[]) {
  const content: any[] = [];
  let h1Counter = 0;

  for (const node of outline) {
    if (node.level === 1) h1Counter++;

    // 章节标题（h2 for level-1，h3 for level-2）
    const headingLevel = node.level === 1 ? 2 : 3;
    const prefix = node.level === 1 ? `${h1Counter}、` : "";
    const lockMark = node.engineLocked ? " 🔒" : "";
    content.push({
      type: "heading",
      attrs: {
        level: headingLevel,
        "data-section-id": node.id,
        "data-engine-locked": node.engineLocked,
      },
      content: [{ type: "text", text: `${prefix}${node.title}${lockMark}` }],
    });

    // 章节内容
    if (node.status === "generating") {
      content.push({
        type: "paragraph",
        attrs: { "data-generating": "true" },
        content: [{ type: "text", text: "⟳ 正在生成内容…" }],
      });
    } else if (!node.content && node.status === "empty") {
      content.push({
        type: "paragraph",
        attrs: { "data-empty": "true" },
        content: [{ type: "text", text: "（此章节内容待生成，可在右侧 AI 助手输入指令）" }],
      });
    } else if (node.engineLocked && node.content) {
      // 引擎内容：解析 Markdown 表格 → Tiptap table
      const parsed = parseEngineContent(node.id, node.content);
      content.push(...parsed);
    } else if (node.content) {
      // LLM 文字内容：解析成段落
      const paras = parseMdToTiptap(node.content);
      content.push(...paras);
    } else {
      content.push({ type: "paragraph", content: [] });
    }
  }

  return { type: "doc", content };
}

// 解析引擎内容（Markdown 表格 → Tiptap table，文本 → paragraph）
function parseEngineContent(id: string, md: string): any[] {
  if (id === "dev-table" || id === "dev-params") {
    return parseMdTable(md);
  }
  if (id === "waste-check") {
    return md.split(/\n\n+/).filter(Boolean).map((block) => ({
      type: "paragraph",
      content: [{ type: "text", text: block.replace(/【(.+?)】/, "[$1] ") }],
    }));
  }
  if (id === "records") {
    return md.split("\n").filter(Boolean).map((line) => ({
      type: "bulletList",
      content: [{
        type: "listItem",
        content: [{
          type: "paragraph",
          content: [{ type: "text", text: line.replace(/^[-•*] /, "") }],
        }],
      }],
    }));
  }
  return parseMdToTiptap(md);
}

// Markdown 表格 → Tiptap table JSON
function parseMdTable(md: string): any[] {
  const lines = md.split("\n").filter((l) => l.trim().startsWith("|"));
  if (lines.length < 2) return [{ type: "paragraph", content: [{ type: "text", text: md }] }];

  const rows: string[][] = [];
  for (const line of lines) {
    const cells = line.split("|").slice(1, -1).map((c) => c.trim());
    if (cells.every((c) => /^[-: ]+$/.test(c))) continue; // separator row
    rows.push(cells);
  }
  if (rows.length === 0) return [];

  const tableContent = rows.map((row, ri) => ({
    type: "tableRow",
    content: row.map((cell) => ({
      type: ri === 0 ? "tableHeader" : "tableCell",
      attrs: { colspan: 1, rowspan: 1, colwidth: null },
      content: [{
        type: "paragraph",
        content: cell ? [{ type: "text", text: cell }] : [],
      }],
    })),
  }));

  return [{ type: "table", content: tableContent }];
}

// Markdown 文字 → Tiptap 段落/标题/列表
function parseMdToTiptap(md: string): any[] {
  if (!md) return [{ type: "paragraph", content: [] }];
  const lines = md.split("\n");
  const nodes: any[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) { nodes.push({ type: "paragraph", content: [] }); i++; continue; }
    if (trimmed.startsWith("### ")) {
      nodes.push({ type: "heading", attrs: { level: 4 }, content: [{ type: "text", text: trimmed.slice(4) }] });
    } else if (trimmed.startsWith("## ")) {
      nodes.push({ type: "heading", attrs: { level: 3 }, content: [{ type: "text", text: trimmed.slice(3) }] });
    } else if (trimmed.startsWith("# ")) {
      nodes.push({ type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: trimmed.slice(2) }] });
    } else if (/^[-•*] /.test(trimmed)) {
      nodes.push({ type: "bulletList", content: [{ type: "listItem", content: [{ type: "paragraph", content: parseBoldText(trimmed.replace(/^[-•*] /, "")) }] }] });
    } else if (/^\d+[.)]\s/.test(trimmed)) {
      nodes.push({ type: "orderedList", content: [{ type: "listItem", content: [{ type: "paragraph", content: parseBoldText(trimmed.replace(/^\d+[.)]\s/, "")) }] }] });
    } else {
      nodes.push({ type: "paragraph", content: parseBoldText(trimmed) });
    }
    i++;
  }
  return nodes.length ? nodes : [{ type: "paragraph", content: [] }];
}

// **bold** → Tiptap marks
function parseBoldText(text: string): any[] {
  const parts = text.split(/(\*\*[^*]+\*\*)/);
  return parts.map((p) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return { type: "text", text: p.slice(2, -2), marks: [{ type: "bold" }] };
    }
    return { type: "text", text: p };
  }).filter((p) => p.text);
}

// ── 从 Tiptap JSON 提取各章节文本（用于保存回 outline） ──────────
function docToOutlineContents(doc: any, _outline: OutlineNode[]): Record<string, string> {
  const map: Record<string, string> = {};
  let currentId: string | null = null;
  let buffer: string[] = [];

  function flush() {
    if (currentId) map[currentId] = buffer.join("\n").trim();
    buffer = [];
  }

  function nodeText(n: any): string {
    if (!n.content) return "";
    return n.content.map((c: any) => c.text ?? nodeText(c)).join("");
  }

  for (const node of doc.content ?? []) {
    if (node.type === "heading" && node.attrs?.["data-section-id"]) {
      flush();
      currentId = node.attrs["data-section-id"];
    } else if (currentId) {
      if (node.type === "paragraph") buffer.push(nodeText(node));
      else if (node.type === "table") {
        const rows = (node.content ?? []).map((row: any) =>
          "| " + (row.content ?? []).map((cell: any) => nodeText(cell.content?.[0] ?? {})).join(" | ") + " |"
        );
        buffer.push(rows.join("\n"));
      } else {
        buffer.push(nodeText(node));
      }
    }
  }
  flush();
  return map;
}

// ── 主组件 ──────────────────────────────────────────────────────
export function BidEditor({ state, setStateRaw, onExport, exporting }: BidEditorProps) {
  const { outline, engineParams } = state;
  const [activeId, setActiveId] = useState(outline[0]?.id ?? "");
  const [chatInput, setChatInput] = useState("");
  const [chatMsgs, setChatMsgs] = useState<{ role: "user" | "ai"; text: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const navRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const totalWords = outline.reduce((s, n) => s + (n.content?.length ?? 0), 0);
  const doneCount = outline.filter((n) => n.status !== "empty").length;

  const editor = useEditor({
    extensions: [
      StarterKit,
      Table.configure({ resizable: false }),
      TableRow,
      TableHeader,
      TableCell,
    ],
    content: outlineToDoc(outline),
    editorProps: {
      attributes: { class: "bid-tiptap-doc" },
    },
    onUpdate: ({ editor }) => {
      // 保存编辑内容回 outline
      const contents = docToOutlineContents(editor.getJSON(), outline);
      setStateRaw((prev) => ({
        ...prev,
        outline: prev.outline.map((n) => {
          const c = contents[n.id];
          if (c === undefined || n.engineLocked) return n;
          return { ...n, content: c, status: "edited" as ContentStatus };
        }),
      }));
    },
  });

  // outline 数据变化时（如生成完成）重新设置编辑器内容
  const prevOutlineRef = useRef<string>("");
  useEffect(() => {
    const sig = outline.map((n) => `${n.id}:${n.status}:${n.content?.length ?? 0}`).join("|");
    if (editor && sig !== prevOutlineRef.current) {
      prevOutlineRef.current = sig;
      const doc = outlineToDoc(outline);
      editor.commands.setContent(doc, false); // false = don't trigger onUpdate
    }
  }, [outline, editor]);

  // IntersectionObserver 更新活跃章节
  useEffect(() => {
    const editorEl = document.querySelector(".bid-tiptap-doc");
    if (!editorEl) return;
    const headings = editorEl.querySelectorAll("[data-section-id]");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const id = (e.target as HTMLElement).dataset.sectionId;
            if (id) setActiveId(id);
          }
        }
      },
      { threshold: 0.5 },
    );
    headings.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [editor]);

  // 点击大纲 → 滚动到章节
  function scrollToSection(id: string) {
    setActiveId(id);
    const editorEl = document.querySelector(".bid-tiptap-doc");
    if (!editorEl) return;
    const heading = editorEl.querySelector(`[data-section-id="${id}"]`);
    if (heading) heading.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // AI 聊天
  async function sendChat() {
    const msg = chatInput.trim();
    if (!msg) return;
    const activeTitle = outline.find((n) => n.id === activeId)?.title ?? "当前章节";
    setChatMsgs((m) => [...m, { role: "user", text: msg }]);
    setChatInput("");
    setChatLoading(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: `针对标书章节「${activeTitle}」：${msg}` }),
      });
      const data = await res.json();
      const reply: string = data.text ?? data.message ?? data.content ?? "（暂无回复）";
      setChatMsgs((m) => [...m, { role: "ai", text: reply }]);
      // 插入到编辑器光标位置
      if (editor) {
        editor.commands.focus("end");
        editor.commands.insertContent("\n" + reply);
      }
    } catch {
      setChatMsgs((m) => [...m, { role: "ai", text: "请求失败，请重试。" }]);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <div className="v3-write-layout">
      {/* 左：章节导航 */}
      <nav className="v3-write-outline">
        <div className="v3-write-outline-head">章节大纲</div>
        <div className="v3-write-nav">
          {outline.map((n) => (
            <div
              key={n.id}
              ref={(el) => { navRefs.current[n.id] = el; }}
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
        <div className="v3-write-nav-footer">
          {doneCount}/{outline.length} 章 · {totalWords.toLocaleString()} 字
        </div>
      </nav>

      {/* 中：A4 文档编辑器 */}
      <div className="v3-write-body">
        <div className="bid-doc-wrap">
          <div className="bid-doc-toolbar">
            <span className="bid-doc-toolbar-title">标书文档</span>
            <div className="bid-doc-toolbar-actions">
              <button
                className="bid-toolbar-btn"
                title="粗体"
                onClick={() => editor?.chain().focus().toggleBold().run()}
                disabled={!editor?.isActive("bold") === undefined}
              >B</button>
              <button
                className="bid-toolbar-btn"
                title="列表"
                onClick={() => editor?.chain().focus().toggleBulletList().run()}
              >≡</button>
              <button
                className="bid-toolbar-btn"
                title="有序列表"
                onClick={() => editor?.chain().focus().toggleOrderedList().run()}
              >1.</button>
              <span className="bid-toolbar-sep" />
              <span className="bid-doc-words">{totalWords.toLocaleString()} 字</span>
            </div>
          </div>
          <div className="bid-doc-scroll">
            <div className="bid-doc-paper">
              <EditorContent editor={editor} />
            </div>
          </div>
        </div>
      </div>

      {/* 右：AI 助手 */}
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
              <p className="muted small" style={{ padding: "0.25rem 0" }}>
                选中文字或定位到章节，在此输入修改指令
              </p>
            )}
            {chatMsgs.map((m, i) => (
              <div key={i} className={m.role === "user" ? "v3-ai-msg-user" : "v3-ai-msg-ai"}>{m.text}</div>
            ))}
            {chatLoading && <div className="muted small">AI 思考中…</div>}
          </div>
          <div className="v3-ai-input">
            <textarea
              value={chatInput}
              placeholder="输入修改指令，例如：把第三段展开，增加技术细节"
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
