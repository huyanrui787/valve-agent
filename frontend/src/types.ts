export interface Health {
  status: string;
  version: string;
  llm: string;
}

export interface LineOutcome {
  input_text: string;
  quantity: number;
  selection?: SelectionResult | null;
  quote?: QuoteLine | null;
  error?: string | null;
  history_hint?: string;
}

export interface SelectionResult {
  condition: Record<string, unknown>;
  candidates: Candidate[];
  rejections: Rejection[];
  material_notes: string[];
}

export interface Candidate {
  product: { code: string; name: string };
  chosen_body_material: string;
  chosen_trim_material: string;
  reasons: string[];
  score: number;
}

export interface Rejection {
  code: string;
  name: string;
  stage: string;
  reason: string;
}

export interface QuoteLine {
  product_code: string;
  product_name: string;
  dn: number;
  quantity: number;
  unit_cost: number;
  unit_price: number;
  line_total: number;
  margin: number;
  pre_tax_unit_price: number;
  cost_lines: { name: string; amount: number; material_key?: string }[];
  warnings: string[];
}

export interface DeviationItem {
  seq: number;
  param: string;
  requirement: string;
  product_capability: string;
  verdict: string;
  is_critical: boolean;
  suggestion: string;
  evidence: string[];
}

export interface BidPackage {
  product_code: string;
  product_name: string;
  deviation_table: {
    items: DeviationItem[];
    negative_count: number;
    critical_negatives: DeviationItem[];
  };
  compliance_report: {
    items: { name: string; level: string; detail: string }[];
    overall: string;
  };
  tech_proposal: string;
  can_bid?: boolean;
}

export interface ParsedTender {
  source: string;
  raw_text?: string;
  brief: {
    title: string;
    bid_deadline?: string | null;
    required_qual_categories: string[];
    min_track_records: number;
    industry_hint: string;
    key_points: string[];
    risks: { clause: string; level: string; summary: string }[];
  };
  requirements: {
    param: string;
    op: string;
    target_value?: number | null;
    target_set?: string[] | null;
    unit: string;
    is_critical: boolean;
    raw: string;
  }[];
  waste_clauses: string[];
}

export interface TenderBidResponse {
  tender: ParsedTender;
  selection?: SelectionResult | null;
  quote_error?: string | null;
  package?: BidPackage | null;
}

export interface RagHit {
  id: string;
  text: string;
  source: string;
  kind: string;
  score: number;
}

// ---- 标书项目记录 ----
export interface ProjectSummary {
  id: string;
  project_name: string;
  status: string;
  word_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends ProjectSummary {
  spec: string;
  snapshot: Record<string, unknown>;
}

export interface ProjectList {
  items: ProjectSummary[];
  total: number;
}

export interface ProjectSave {
  project_name: string;
  word_count?: number;
  spec?: string;
  status?: string;
  snapshot?: Record<string, unknown>;
}
export interface ChatStatus {
  available: boolean;
}

export type AgentEventType =
  | "session"
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "await_confirm"
  | "message"
  | "error"
  | "done";

export interface AgentEvent {
  type: AgentEventType;
  step?: number;
  // session / done
  session_id?: string;
  // thinking / message
  text?: string;
  // tool_call / tool_result / await_confirm
  call_id?: string;
  tool?: string;
  arguments?: Record<string, unknown>;
  is_write?: boolean;
  ok?: boolean;
  result?: unknown;
  error?: string;
  prompt?: string;
  // error
  message?: string;
  downgrade?: boolean;
}
