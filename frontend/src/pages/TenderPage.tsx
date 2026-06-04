import { useState } from "react";
import { postTenderParse } from "../api/client";
import type { ParsedTender } from "../types";

export function TenderPage() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [parsed, setParsed] = useState<ParsedTender | null>(null);

  async function runParse() {
    if (!file) {
      setError("请选择文件");
      return;
    }
    setLoading(true);
    setError("");
    try {
      setParsed(await postTenderParse(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h2 className="page-title">招标解析</h2>
      <p className="page-desc">
        上传 PDF/Word,自动抽取技术参数、资质业绩要求、废标条款与要点清单。
      </p>

      <div className="card">
        <label>招标文件</label>
        <input
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button className="btn" disabled={loading || !file} onClick={runParse}>
          解析
        </button>
        {error && <p className="error">{error}</p>}
      </div>

      {parsed && (
        <>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>要点清单</h3>
            <p>
              <strong>{parsed.brief.title || "未识别标题"}</strong>
            </p>
            <ul>
              {parsed.brief.key_points.map((p, i) => (
                <li key={i}>{p}</li>
              ))}
            </ul>
            <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
              资质: {parsed.brief.required_qual_categories.join(", ") || "无"} ·
              最少业绩 {parsed.brief.min_track_records} 项 · 行业{" "}
              {parsed.brief.industry_hint || "未识别"}
            </p>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>技术要求</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>参数</th>
                    <th>要求</th>
                    <th>关键</th>
                  </tr>
                </thead>
                <tbody>
                  {parsed.requirements.map((r, i) => (
                    <tr key={i}>
                      <td>{r.param}</td>
                      <td>
                        {r.target_value != null
                          ? `${r.op} ${r.target_value}${r.unit}`
                          : `∈ ${(r.target_set ?? []).join(", ")}`}
                      </td>
                      <td>{r.is_critical ? "★" : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {parsed.waste_clauses.length > 0 && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>废标摘录</h3>
              <ul>
                {parsed.waste_clauses.map((c, i) => (
                  <li key={i} style={{ color: "var(--warn)", fontSize: "0.88rem" }}>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </>
  );
}
