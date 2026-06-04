import { useState } from "react";
import {
  downloadBidDocx,
  postTenderBid,
  saveBlob,
} from "../api/client";
import type { TenderBidResponse } from "../types";

const DEMO_SPEC = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316";

export function BidPage() {
  const [spec, setSpec] = useState(DEMO_SPEC);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<TenderBidResponse | null>(null);

  async function runBid() {
    setLoading(true);
    setError("");
    try {
      setResult(await postTenderBid(spec, file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runExport() {
    setLoading(true);
    setError("");
    try {
      const blob = await downloadBidDocx(spec, file);
      saveBlob(blob, "bid_package.docx");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const pkg = result?.package;
  const canBid =
    pkg &&
    !pkg.compliance_report.items.some((i) => i.level === "高风险");

  return (
    <>
      <h2 className="page-title">标书应答</h2>
      <p className="page-desc">
        上传招标文件(可选) + 选型工况 → 技术偏离表、废标体检、技术方案初稿。
      </p>

      <div className="card">
        <label>工况描述</label>
        <textarea value={spec} onChange={(e) => setSpec(e.target.value)} />
        <label>招标文件 (PDF / Word / 文本)</label>
        <input
          type="file"
          accept=".pdf,.docx,.doc,.txt,.md"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button className="btn" disabled={loading} onClick={runBid}>
          生成应答包
        </button>{" "}
        <button className="btn secondary" disabled={loading || !pkg} onClick={runExport}>
          导出 Word 初稿
        </button>
        {error && <p className="error">{error}</p>}
        {result?.quote_error && <p className="error">{result.quote_error}</p>}
      </div>

      {result?.tender?.brief?.title && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>招标摘要</h3>
          <p>
            <strong>{result.tender.brief.title}</strong>
            {result.tender.brief.bid_deadline &&
              ` · 截止 ${result.tender.brief.bid_deadline}`}
          </p>
          <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
            技术要求 {result.tender.requirements.length} 条 · 废标摘录{" "}
            {result.tender.waste_clauses.length} 条
          </p>
        </div>
      )}

      {pkg && (
        <>
          <div className="card">
            <h3 style={{ marginTop: 0 }}>投标结论</h3>
            <p>
              型号: <strong>{pkg.product_code}</strong> {pkg.product_name} ·
              关键负偏离: {pkg.deviation_table.critical_negatives.length} ·
              <span style={{ color: canBid ? "var(--ok)" : "var(--fail)" }}>
                {canBid ? " 可投标" : " 存在高风险废标项"}
              </span>
            </p>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>技术偏离表</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>#</th>
                    <th>参数</th>
                    <th>招标要求</th>
                    <th>产品能力</th>
                    <th>判定</th>
                  </tr>
                </thead>
                <tbody>
                  {pkg.deviation_table.items.map((i) => (
                    <tr key={i.seq}>
                      <td>{i.seq}</td>
                      <td>
                        {i.param}
                        {i.is_critical ? " ★" : ""}
                      </td>
                      <td>{i.requirement}</td>
                      <td>{i.product_capability}</td>
                      <td className={`verdict-${i.verdict}`}>{i.verdict}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>废标风险体检</h3>
            <ul style={{ margin: 0, paddingLeft: "1.2rem" }}>
              {pkg.compliance_report.items.map((i, idx) => (
                <li key={idx} style={{ marginBottom: "0.35rem" }}>
                  <strong>[{i.level}]</strong> {i.name}: {i.detail}
                </li>
              ))}
            </ul>
          </div>

          {pkg.tech_proposal && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>技术方案概述</h3>
              <p style={{ whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>
                {pkg.tech_proposal}
              </p>
            </div>
          )}
        </>
      )}
    </>
  );
}
