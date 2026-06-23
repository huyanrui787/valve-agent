import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects } from "../api/client";
import type { ProjectSummary } from "../types";

/** 把字数转成「万字」展示,对齐竞品。 */
function wanZi(n: number): string {
  if (n <= 0) return "0 字";
  if (n < 10000) return `${n.toLocaleString()} 字`;
  return `${(n / 10000).toFixed(2)} 万字`;
}

/** ISO 时间 → "YYYY-MM-DD HH:mm"。 */
function fmtTime(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (x: number) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const STATUS_LABEL: Record<string, string> = {
  completed: "已完成",
  draft: "草稿",
};

export function ProjectsPage() {
  const nav = useNavigate();
  const [items, setItems] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [keyword, setKeyword] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const res = await listProjects();
      setItems(res.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  const filtered = keyword.trim()
    ? items.filter((p) => p.project_name.includes(keyword.trim()))
    : items;

  return (
    <>
      <div className="proj-head">
        <h2 className="page-title" style={{ margin: 0 }}>我的标书</h2>
        <div className="proj-head-right">
          <span className="proj-total">标书总数 · {items.length}</span>
          <button className="btn" onClick={() => nav("/bid")}>+ 新建标书</button>
        </div>
      </div>
      <p className="page-desc">标书内容生成后自动归档,可随时重新打开继续编辑或导出。</p>

      <div className="card proj-toolbar">
        <input
          className="proj-search"
          placeholder="搜索标书 / 项目名称…"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
        <button className="btn secondary btn-sm" onClick={() => void load()}>刷新</button>
      </div>

      {error && <p className="error">{error}</p>}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="table-wrap">
          <table className="proj-table">
            <thead>
              <tr>
                <th>项目名称</th>
                <th>状态</th>
                <th>已消耗字数</th>
                <th>最后更新</th>
                <th style={{ textAlign: "right" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => (
                <tr key={p.id}>
                  <td>
                    <span className="proj-name" onClick={() => nav(`/bid?pid=${p.id}`)}>
                      {p.project_name}
                    </span>
                  </td>
                  <td>
                    <span className={`proj-status ${p.status}`}>
                      ✓ {STATUS_LABEL[p.status] ?? p.status}
                    </span>
                  </td>
                  <td><span className="proj-words">{wanZi(p.word_count)}</span></td>
                  <td className="proj-time">{fmtTime(p.updated_at)}</td>
                  <td style={{ textAlign: "right" }}>
                    <button className="proj-action" onClick={() => nav(`/bid?pid=${p.id}`)}>
                      编辑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!loading && filtered.length === 0 && (
          <div className="proj-empty">
            {items.length === 0
              ? "还没有标书。点击「新建标书」生成第一份。"
              : "没有匹配的标书。"}
          </div>
        )}
        {loading && <div className="proj-empty">加载中…</div>}
      </div>
    </>
  );
}
