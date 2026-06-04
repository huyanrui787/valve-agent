import { useState } from "react";
import {
  downloadQuoteDocx,
  postQuote,
  postSelect,
  saveBlob,
} from "../api/client";
import type { LineOutcome, SelectionResult } from "../types";

const DEMO_SPEC = "球阀 DN200 PN40 蒸汽 250℃ 电动 API 316";

export function QuotePage() {
  const [spec, setSpec] = useState(DEMO_SPEC);
  const [qty, setQty] = useState(10);
  const [tier, setTier] = useState("A");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<SelectionResult | null>(null);
  const [outcome, setOutcome] = useState<LineOutcome | null>(null);

  async function runSelect() {
    setLoading(true);
    setError("");
    try {
      setSelection(await postSelect(spec));
      setOutcome(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function runQuote() {
    setLoading(true);
    setError("");
    try {
      const oc = await postQuote({ spec, quantity: qty, customer_tier: tier });
      setOutcome(oc);
      if (oc.selection) setSelection(oc.selection);
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
      const blob = await downloadQuoteDocx({
        spec,
        quantity: qty,
        customer_tier: tier,
      });
      saveBlob(blob, "quotation.docx");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  const q = outcome?.quote;

  return (
    <>
      <h2 className="page-title">智能报价</h2>
      <p className="page-desc">
        自然语言选型 + BOM 成本核算 + 毛利定价。规则引擎保证准确，结果可导出 Word。
      </p>

      <div className="card">
        <label>工况描述</label>
        <textarea value={spec} onChange={(e) => setSpec(e.target.value)} />
        <div className="row">
          <div>
            <label>数量</label>
            <input
              type="number"
              min={1}
              value={qty}
              onChange={(e) => setQty(Number(e.target.value))}
            />
          </div>
          <div>
            <label>客户等级</label>
            <select value={tier} onChange={(e) => setTier(e.target.value)}>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
            </select>
          </div>
        </div>
        <button className="btn secondary" disabled={loading} onClick={runSelect}>
          选型
        </button>{" "}
        <button className="btn" disabled={loading} onClick={runQuote}>
          生成报价
        </button>{" "}
        <button className="btn secondary" disabled={loading} onClick={runExport}>
          导出 Word
        </button>
        {error && <p className="error">{error}</p>}
      </div>

      {selection && selection.candidates.length > 0 && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>选型候选</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>型号</th>
                  <th>名称</th>
                  <th>材质</th>
                  <th>依据</th>
                </tr>
              </thead>
              <tbody>
                {selection.candidates.map((c) => (
                  <tr key={c.product.code}>
                    <td>{c.product.code}</td>
                    <td>{c.product.name}</td>
                    <td>
                      {c.chosen_body_material}/{c.chosen_trim_material}
                    </td>
                    <td>{c.reasons.slice(0, 2).join("; ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {q && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>报价结果</h3>
          <div className="metric-grid">
            <div className="metric">
              <div className="val">{q.product_code}</div>
              <div className="lbl">选定型号</div>
            </div>
            <div className="metric">
              <div className="val">¥{q.unit_price.toLocaleString()}</div>
              <div className="lbl">含税单价</div>
            </div>
            <div className="metric">
              <div className="val">¥{q.line_total.toLocaleString()}</div>
              <div className="lbl">行合计</div>
            </div>
            <div className="metric">
              <div className="val">{(q.margin * 100).toFixed(1)}%</div>
              <div className="lbl">毛利率</div>
            </div>
          </div>
          {outcome?.history_hint && (
            <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
              {outcome.history_hint}
            </p>
          )}
        </div>
      )}

      {outcome?.error && <p className="error">{outcome.error}</p>}
    </>
  );
}
