/** 标书智能体 v3 — 状态类型 */

export type BidStep = "upload" | "parse" | "outline" | "write";

// ── 解析结果结构 ──────────────────────────────────────────────────
export interface ParsedInfo {
  projectName: string;
  projectNo: string;
  deadline: string;
  owner: string;
  agency: string;
  budget: string;
  qualifications: string[];
  techRequirements: { param: string; value: string; critical: boolean }[];
  wasteItems: string[];
  scoringItems: { name: string; score: number; desc: string }[];
  keyDates: { name: string; time: string }[];
  bondInfo: string;
}

// ── 目录章节 ──────────────────────────────────────────────────────
export type OutlineNodeType = "heading1" | "heading2";
export type ContentStatus = "empty" | "generating" | "done" | "edited";

export interface OutlineNode {
  id: string;
  title: string;
  level: 1 | 2;
  /** true = 引擎确定性生成，锁定不可自由编辑 */
  engineLocked: boolean;
  /** 预估字数 */
  wordHint: number;
  status: ContentStatus;
  content: string;
}

// ── 整体文档状态 ─────────────────────────────────────────────────
export interface BidV3State {
  step: BidStep;
  projectName: string;

  /** 已归档的项目记录 id;内容生成后写入,此后编辑/导出更新同一条 */
  projectId: string | null;

  // Step1
  tenderFile: File | null;
  boqFile: File | null;

  // Step2
  parsedInfo: ParsedInfo | null;
  rawText: string; // 招标文件原文（用于左栏预览）

  // Step3
  outline: OutlineNode[];

  // Step4
  activeNodeId: string;

  // 关键参数（引擎锁定）
  engineParams: EngineParams | null;
}

export interface EngineParams {
  productCode: string;
  productName: string;
  deviationCount: number;
  criticalNeg: number;
  canBid: boolean;
}

// ── 默认目录模板 ──────────────────────────────────────────────────
export const DEFAULT_OUTLINE: Omit<OutlineNode, "status" | "content">[] = [
  { id: "dev-table",   title: "技术偏离表",         level: 1, engineLocked: true,  wordHint: 1500 },
  { id: "dev-params",  title: "关键参数逐一对比",   level: 2, engineLocked: true,  wordHint: 800  },
  { id: "dev-stmt",    title: "技术规范偏离说明",   level: 2, engineLocked: false, wordHint: 600  },
  { id: "proposal",    title: "技术方案完整性",     level: 1, engineLocked: false, wordHint: 3000 },
  { id: "prod-pos",    title: "产品定位与适用场景", level: 2, engineLocked: false, wordHint: 800  },
  { id: "prod-param",  title: "核心参数与结构特点", level: 2, engineLocked: false, wordHint: 1000 },
  { id: "prod-std",    title: "标准合规性与质量保障",level: 2, engineLocked: false, wordHint: 600  },
  { id: "quality",     title: "产品质量与业绩",     level: 1, engineLocked: false, wordHint: 2000 },
  { id: "records",     title: "近三年典型业绩",     level: 2, engineLocked: true,  wordHint: 800  },
  { id: "certs",       title: "质量体系认证",       level: 2, engineLocked: false, wordHint: 400  },
  { id: "service",     title: "售后服务能力",       level: 1, engineLocked: false, wordHint: 1200 },
  { id: "svc-time",    title: "服务响应时间承诺",   level: 2, engineLocked: false, wordHint: 400  },
  { id: "svc-parts",   title: "备件供应方案",       level: 2, engineLocked: false, wordHint: 400  },
  { id: "waste-check", title: "废标风险自检报告",   level: 1, engineLocked: true,  wordHint: 600  },
];

export function initOutline(): OutlineNode[] {
  return DEFAULT_OUTLINE.map((n) => ({ ...n, status: "empty" as ContentStatus, content: "" }));
}

export function initState(): BidV3State {
  return {
    step: "upload",
    projectName: "",
    projectId: null,
    tenderFile: null,
    boqFile: null,
    parsedInfo: null,
    rawText: "",
    outline: initOutline(),
    activeNodeId: "dev-table",
    engineParams: null,
  };
}
