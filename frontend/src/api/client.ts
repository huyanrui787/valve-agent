import type {
  AgentEvent,
  ChatStatus,
  Health,
  LineOutcome,
  ParsedTender,
  ProjectDetail,
  ProjectList,
  ProjectSave,
  RagHit,
  SelectionResult,
  TenderBidResponse,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail),
    );
  }
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<Health> {
  return json(await fetch(`${BASE}/api/health`));
}

export async function postSelect(spec: string, topN = 3): Promise<SelectionResult> {
  return json(
    await fetch(`${BASE}/api/quote/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec, top_n: topN }),
    }),
  );
}

export async function postQuote(body: {
  spec: string;
  quantity?: number;
  customer_tier?: string;
  customer?: string;
}): Promise<LineOutcome> {
  return json(
    await fetch(`${BASE}/api/quote/line`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        quantity: 1,
        customer_tier: "C",
        ...body,
      }),
    }),
  );
}

export async function postTenderParse(file: File): Promise<ParsedTender> {
  const fd = new FormData();
  fd.append("file", file);
  return json(
    await fetch(`${BASE}/api/tender/parse`, { method: "POST", body: fd }),
  );
}

export async function postTenderBid(
  spec: string,
  file?: File | null,
  customer = "",
): Promise<TenderBidResponse> {
  const fd = new FormData();
  fd.append("spec", spec);
  fd.append("customer", customer);
  if (file) fd.append("file", file);
  return json(
    await fetch(`${BASE}/api/tender/bid`, { method: "POST", body: fd }),
  );
}

export async function postRagSearch(query: string, topK = 5): Promise<{
  embedder: string;
  hits: RagHit[];
}> {
  return json(
    await fetch(`${BASE}/api/rag/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, top_k: topK }),
    }),
  );
}

export async function downloadQuoteDocx(body: {
  spec: string;
  quantity?: number;
  customer_tier?: string;
  customer?: string;
}): Promise<Blob> {
  const res = await fetch(`${BASE}/api/export/quote`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quantity: 1, customer_tier: "C", ...body }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.blob();
}

export async function downloadBidDocx(
  spec: string,
  file?: File | null,
  customer = "",
): Promise<Blob> {
  const fd = new FormData();
  fd.append("spec", spec);
  fd.append("customer", customer);
  if (file) fd.append("file", file);
  const res = await fetch(`${BASE}/api/export/bid`, { method: "POST", body: fd });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.blob();
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// 标书项目记录(内容生成后留存,可重新打开续编)
// ---------------------------------------------------------------------------
export async function listProjects(): Promise<ProjectList> {
  return json(await fetch(`${BASE}/api/projects`));
}

export async function getProject(id: string): Promise<ProjectDetail> {
  return json(await fetch(`${BASE}/api/projects/${id}`));
}

export async function createProject(body: ProjectSave): Promise<ProjectDetail> {
  return json(
    await fetch(`${BASE}/api/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateProject(
  id: string,
  body: ProjectSave,
): Promise<ProjectDetail> {
  return json(
    await fetch(`${BASE}/api/projects/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

// ---------------------------------------------------------------------------
// 对话式 Agent(SSE over POST)
// ---------------------------------------------------------------------------
export async function fetchChatStatus(): Promise<ChatStatus> {
  return json(await fetch(`${BASE}/api/chat/status`));
}

/** 读取 POST 返回的 SSE 流,逐个事件回调。EventSource 只支持 GET,故手动解析。 */
async function readSse(
  res: Response,
  onEvent: (ev: AgentEvent) => void,
): Promise<void> {
  if (!res.ok || !res.body) {
    throw new Error(`SSE 连接失败:${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE 以空行分隔事件块
    let idx: number;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let type = "";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) type = line.slice(7).trim();
        else if (line.startsWith("data: ")) data = line.slice(6);
      }
      if (!type) continue;
      let parsed: Record<string, unknown> = {};
      try {
        parsed = data ? JSON.parse(data) : {};
      } catch {
        parsed = {};
      }
      onEvent({ type: type as AgentEvent["type"], ...parsed });
    }
  }
}

export async function streamChat(
  message: string,
  onEvent: (ev: AgentEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  await readSse(res, onEvent);
}

export async function streamChatConfirm(
  sessionId: string,
  callId: string,
  approved: boolean,
  onEvent: (ev: AgentEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/chat/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, call_id: callId, approved }),
  });
  await readSse(res, onEvent);
}
