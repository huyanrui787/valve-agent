// 工具名 → 中文标签 + 图标,集中管理
export const TOOL_LABELS: Record<string, { label: string; icon: string }> = {
  select_valve: { label: "选型", icon: "🔍" },
  quote: { label: "报价核算", icon: "💰" },
  assess_compliance: { label: "技术偏离表", icon: "📋" },
  check_waste_bid: { label: "废标自检", icon: "🛡️" },
  rag_search: { label: "知识检索", icon: "📚" },
  export_quote_docx: { label: "导出报价单", icon: "📄" },
  sync_crm: { label: "同步 CRM", icon: "🔄" },
};

export function toolLabel(name: string): { label: string; icon: string } {
  return TOOL_LABELS[name] ?? { label: name, icon: "🔧" };
}

export function money(x: number): string {
  return "¥" + x.toLocaleString("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
