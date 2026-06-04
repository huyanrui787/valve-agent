import type {
  Health,
  LineOutcome,
  ParsedTender,
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
