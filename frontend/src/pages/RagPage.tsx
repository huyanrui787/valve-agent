import { useState } from "react";
import { postRagSearch } from "../api/client";
import type { RagHit } from "../types";

export function RagPage() {
  const [query, setQuery] = useState("球阀 蒸汽 API 电力业绩");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [embedder, setEmbedder] = useState("");
  const [hits, setHits] = useState<RagHit[]>([]);

  async function runSearch() {
    setLoading(true);
    setError("");
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
        RAG 检索产品库、资质、业绩与招标片段。离线使用哈希向量,配置 DashScope 后自动升级 Qwen。
      </p>

      <div className="card">
        <label>检索问句</label>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn" disabled={loading} onClick={runSearch}>
          检索
        </button>
        {error && <p className="error">{error}</p>}
        {embedder && (
          <p style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
            embedder: {embedder}
          </p>
        )}
      </div>

      {hits.length > 0 && (
        <div className="card">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>分数</th>
                  <th>类型</th>
                  <th>来源</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                {hits.map((h) => (
                  <tr key={h.id}>
                    <td>{h.score.toFixed(3)}</td>
                    <td>{h.kind}</td>
                    <td>{h.source}</td>
                    <td>{h.text.slice(0, 120)}…</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
