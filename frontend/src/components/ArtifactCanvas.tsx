import type { AgentEvent } from "../types";
import { money, toolLabel } from "./toolMeta";

interface Props {
  artifacts: AgentEvent[]; // 已完成且可渲染的 tool_result 事件,按时间倒序展示
}

/** 右侧画布:把工具结果渲染为结构化卡片(报价表/偏离表/选型/废标)。 */
export function ArtifactCanvas({ artifacts }: Props) {
  if (artifacts.length === 0) {
    return (
      <div className="canvas-empty">
        <p>结构化产物会显示在这里</p>
        <p className="muted">
          报价单、技术偏离表、选型结果、废标体检报告等
        </p>
      </div>
    );
  }
  return (
    <div className="canvas-stack">
      {artifacts.map((a, i) => (
        <ArtifactCard key={`${a.call_id}-${i}`} ev={a} />
      ))}
    </div>
  );
}

function ArtifactCard({ ev }: { ev: AgentEvent }) {
  const meta = toolLabel(ev.tool ?? "");
  const r = (ev.result ?? {}) as Record<string, any>;
  return (
    <div className="artifact">
      <div className="artifact-head">
        <span>{meta.icon}</span>
        <strong>{meta.label}</strong>
      </div>
      <ArtifactBody tool={ev.tool ?? ""} r={r} />
    </div>
  );
}

function ArtifactBody({ tool, r }: { tool: string; r: Record<string, any> }) {
  if (r.error) return <p className="error">{r.error}</p>;

  if (tool === "quote") {
    return (
      <>
        <p className="artifact-title">
          {r.product_code} · {r.product_name}
        </p>
        <div className="metric-grid compact">
          <Metric lbl="含税单价" val={money(r.unit_price)} strong />
          <Metric lbl="单台成本" val={money(r.unit_cost)} />
          <Metric lbl="实际毛利" val={`${(r.margin * 100).toFixed(1)}%`} />
          <Metric lbl={`整单 ×${r.quantity}`} val={money(r.line_total)} strong />
        </div>
        {Array.isArray(r.warnings) && r.warnings.length > 0 && (
          <ul className="warn-list">
            {r.warnings.map((w: string, i: number) => (
              <li key={i}>⚠ {w}</li>
            ))}
          </ul>
        )}
      </>
    );
  }

  if (tool === "select_valve") {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>型号</th>
              <th>名称</th>
              <th>阀体/阀芯</th>
            </tr>
          </thead>
          <tbody>
            {(r.candidates ?? []).map((c: any) => (
              <tr key={c.code}>
                <td>{c.rank}</td>
                <td>{c.code}</td>
                <td>{c.name}</td>
                <td>
                  {c.body_material}/{c.trim_material}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {r.rejected_count > 0 && (
          <p className="muted small">淘汰 {r.rejected_count} 个型号</p>
        )}
      </div>
    );
  }

  if (tool === "assess_compliance") {
    return (
      <>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>参数</th>
                <th>要求</th>
                <th>能力</th>
                <th>判定</th>
                <th>关键</th>
              </tr>
            </thead>
            <tbody>
              {(r.items ?? []).map((it: any, i: number) => (
                <tr key={i}>
                  <td>{it.param}</td>
                  <td>{it.requirement}</td>
                  <td>{it.capability}</td>
                  <td className={`verdict-${it.verdict}`}>{it.verdict}</td>
                  <td>{it.is_critical ? "★" : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          负偏离 {r.negative_count} 项,关键负偏离{" "}
          <span className={r.critical_negative_count ? "verdict-负偏离" : ""}>
            {r.critical_negative_count}
          </span>{" "}
          项
        </p>
      </>
    );
  }

  if (tool === "check_waste_bid") {
    return (
      <>
        <p className="artifact-title">
          总体:
          <span className={r.overall === "高风险" ? "verdict-负偏离" : ""}>
            {" "}
            {r.overall}
          </span>{" "}
          (高风险 {r.fail_count} · 预警 {r.warn_count})
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>检查项</th>
                <th>等级</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {(r.items ?? []).map((it: any, i: number) => (
                <tr key={i}>
                  <td>{it.name}</td>
                  <td className={levelClass(it.level)}>{it.level}</td>
                  <td>{it.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    );
  }

  if (tool === "rag_search") {
    return (
      <ul className="hit-list">
        {(r.hits ?? []).map((h: any, i: number) => (
          <li key={i}>
            <span className="muted small">
              [{h.kind}] {h.score}
            </span>
            <div>{h.text}</div>
          </li>
        ))}
      </ul>
    );
  }

  if (tool === "export_quote_docx") {
    return (
      <p>
        已生成 Word:<code>{r.path}</code>
      </p>
    );
  }
  if (tool === "sync_crm") {
    return (
      <p>
        已回填 CRM:<code>{r.external_id}</code>
      </p>
    );
  }

  return <pre className="tool-pre">{JSON.stringify(r, null, 2)}</pre>;
}

function levelClass(level: string): string {
  if (level === "高风险") return "verdict-负偏离";
  if (level === "预警") return "level-warn";
  return "verdict-满足";
}

function Metric({ lbl, val, strong }: { lbl: string; val: string; strong?: boolean }) {
  return (
    <div className="metric">
      <div className={strong ? "val strong" : "val"}>{val}</div>
      <div className="lbl">{lbl}</div>
    </div>
  );
}
