import { useState } from "react";
import { postRagSearch } from "../api/client";
import type { RagHit } from "../types";

export function RagPage() {
  const [query, setQuery] = useState("球阀 蒸汽 API 电力业绩");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [embedder, setEmbedder] = useState("");
  const [hits, setHits] = useState<RagHit[] | null>(null);

  async function runSearch() {
    if (!query.trim() || loading) return;
    setLoading(true);
    setError("");
    setHits(null);
    try {
      const res = await postRagSearch(query);
      setEmbedder(res.embedder);
      setHits(res.hits);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h2 className="page-title">知识检索</h2>
      <p className="page-desc">
        RAG 检索产品库、资质、业绩与招标片段。离线使用哈希向量，配置 DashScope 后自动升级 Qwen。
      </p>

      <div className="card">
        <label>检索问句</label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
          disabled={loading}
        />
        <button className="btn" disabled={loading || !query.trim()} onClick={runSearch}>
          {loading ? "检索中…" : "检索"}
        </button>

        {error && <p className="error" style={{ marginTop: "0.75rem" }}>{error}</p>}

        {/* 结果内联展示，避免需要滚动才能看到 */}
        {loading && (
          <div style={{ marginTop: "1rem", color: "var(--muted)", fontSize: "0.85rem" }}>
            正在向量检索…
          </div>
        )}

        {hits !== null && !loading && (
          <div style={{ marginTop: "1rem" }}>
            {embedder && (
              <p style={{ fontSize: "0.75rem", color: "var(--muted)", marginBottom: "0.75rem" }}>
                embedder: {embedder} · {hits.length} 条结果
              </p>
            )}
            {hits.length === 0 ? (
              <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>未找到相关内容。</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>分数</th>
                      <th>类型</th>
                      <th>内容</th>
                    </tr>
                  </thead>
                  <tbody>
                    {hits.map((h) => (
                      <tr key={h.id}>
                        <td style={{ whiteSpace: "nowrap" }}>{h.score.toFixed(3)}</td>
                        <td style={{ whiteSpace: "nowrap" }}>{h.kind}</td>
                        <td>{h.text.slice(0, 160)}{h.text.length > 160 ? "…" : ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}
