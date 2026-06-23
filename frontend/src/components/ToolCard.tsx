import { useState } from "react";
import type { AgentEvent } from "../types";
import { toolLabel } from "./toolMeta";

interface Props {
  call: AgentEvent; // tool_call 事件
  result?: AgentEvent; // 对应的 tool_result(可能尚未到达)
  pending?: boolean; // 等待确认中
}

/** 对话流里的可折叠工具卡片:工具名 + 入参 + 结果摘要,点开看完整 JSON。 */
export function ToolCard({ call, result, pending }: Props) {
  const [open, setOpen] = useState(false);
  const meta = toolLabel(call.tool ?? "");
  const ok = result?.ok ?? true;
  const status = pending
    ? "待确认"
    : result
    ? ok
      ? "完成"
      : "失败"
    : "执行中…";
  const statusClass = pending
    ? "tool-status warn"
    : result
    ? ok
      ? "tool-status ok"
      : "tool-status fail"
    : "tool-status";

  return (
    <div className={`tool-card${call.is_write ? " write" : ""}`}>
      <button className="tool-head" onClick={() => setOpen((v) => !v)}>
        <span className="tool-icon">{meta.icon}</span>
        <span className="tool-name">{meta.label}</span>
        {call.is_write && <span className="tool-badge">写操作</span>}
        <span className={statusClass}>{status}</span>
        <span className="tool-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="tool-body">
          <div className="tool-section-label">入参</div>
          <pre className="tool-pre">
            {JSON.stringify(call.arguments ?? {}, null, 2)}
          </pre>
          {result && (
            <>
              <div className="tool-section-label">
                结果{!ok && <span className="error-inline"> · {result.error}</span>}
              </div>
              <pre className="tool-pre">
                {JSON.stringify(result.result ?? {}, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
