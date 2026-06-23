/**
 * 标书文档状态管理
 * 文档由若干 Section 构成，每个 Section 对应标书的一章。
 * 内容用纯文本（Markdown 子集），渲染时解析。
 */

export type SectionStatus = "empty" | "generating" | "done" | "edited";

export interface DocSection {
  id: string;
  title: string;
  content: string;
  status: SectionStatus;
  /** 是否为引擎确定性生成（不可自由编辑结构，只展示） */
  engineDriven: boolean;
}

export interface BidDocState {
  sections: DocSection[];
  /** 当前聚焦章节 id */
  activeId: string;
  /** 关键参数（引擎锁定） */
  params: BidParams | null;
}

export interface BidParams {
  productCode: string;
  productName: string;
  dn: number;
  pn: number;
  medium: string;
  temp: string;
  drive: string;
  material: string;
  deviationCount: number;
  criticalNegative: number;
  canBid: boolean;
}

export const DEFAULT_SECTIONS: Omit<DocSection, "content" | "status">[] = [
  { id: "deviation",   title: "技术偏离表",   engineDriven: true  },
  { id: "waste",       title: "废标自检报告", engineDriven: true  },
  { id: "proposal",   title: "技术方案概述", engineDriven: false },
  { id: "quality",    title: "质量保证",     engineDriven: false },
  { id: "records",    title: "业绩清单",     engineDriven: false },
];

export function initDoc(): BidDocState {
  return {
    sections: DEFAULT_SECTIONS.map((s) => ({
      ...s,
      content: "",
      status: "empty",
    })),
    activeId: "deviation",
    params: null,
  };
}

export type DocAction =
  | { type: "SET_STATUS"; id: string; status: SectionStatus }
  | { type: "SET_CONTENT"; id: string; content: string }
  | { type: "APPEND_CONTENT"; id: string; delta: string }
  | { type: "SET_ACTIVE"; id: string }
  | { type: "SET_PARAMS"; params: BidParams }
  | { type: "RESET" };

export function docReducer(state: BidDocState, action: DocAction): BidDocState {
  switch (action.type) {
    case "SET_STATUS":
      return {
        ...state,
        sections: state.sections.map((s) =>
          s.id === action.id ? { ...s, status: action.status } : s
        ),
      };
    case "SET_CONTENT":
      return {
        ...state,
        sections: state.sections.map((s) =>
          s.id === action.id
            ? { ...s, content: action.content, status: "done" }
            : s
        ),
      };
    case "APPEND_CONTENT":
      return {
        ...state,
        sections: state.sections.map((s) =>
          s.id === action.id
            ? { ...s, content: s.content + action.delta, status: "generating" }
            : s
        ),
      };
    case "SET_ACTIVE":
      return { ...state, activeId: action.id };
    case "SET_PARAMS":
      return { ...state, params: action.params };
    case "RESET":
      return initDoc();
    default:
      return state;
  }
}
