"""基于 JSON 文件的 ERP/CRM 同步适配器(演示与联调占位)。

生产环境可替换为 HTTP/Webhook 对接真实 ERP/CRM;本实现把报价单与投标快照
写入 sync_dir,便于验收"回填"流程而不依赖外部系统。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from ..agents.bid_agent import BidPackage
from ..engines import Quotation
from .base import SyncResult


class FileSyncAdapter:
    """同时实现 CRM(报价) 与 ERP(成本/投标快照) 的文件落盘。"""

    name = "file-sync"

    def __init__(self, sync_dir: str | Path) -> None:
        self.root = Path(sync_dir)
        self.crm_dir = self.root / "crm" / "quotations"
        self.erp_quote_dir = self.root / "erp" / "quotations"
        self.erp_bid_dir = self.root / "erp" / "bids"

    def push_quotation(self, quote: Quotation, *, customer: str = "") -> SyncResult:
        self.crm_dir.mkdir(parents=True, exist_ok=True)
        cid = customer or quote.customer or "anonymous"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext_id = f"CRM-{ts}"
        payload = {
            "external_id": ext_id,
            "customer": cid,
            "customer_tier": quote.customer_tier,
            "price_basis": str(quote.price_basis or date.today()),
            "total": quote.total,
            "overall_margin": quote.overall_margin,
            "lines": [
                {
                    "product_code": l.product_code,
                    "product_name": l.product_name,
                    "dn": l.dn,
                    "quantity": l.quantity,
                    "unit_price": l.unit_price,
                    "line_total": l.line_total,
                    "margin": l.margin,
                }
                for l in quote.lines
            ],
        }
        path = self.crm_dir / f"{ext_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return SyncResult(ok=True, external_id=ext_id, message="已写入 CRM 同步目录",
                          payload_path=str(path))

    def push_quotation_cost(self, quote: Quotation, *, project_code: str = "") -> SyncResult:
        self.erp_quote_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext_id = f"ERP-Q-{ts}"
        payload = {
            "external_id": ext_id,
            "project_code": project_code or "DEFAULT",
            "total_cost": quote.total_cost,
            "lines": [
                {
                    "product_code": l.product_code,
                    "unit_cost": l.unit_cost,
                    "material_cost": l.material_cost,
                    "cost_lines": [
                        {"name": c.name, "amount": c.amount, "material_key": c.material_key}
                        for c in l.cost_lines
                    ],
                }
                for l in quote.lines
            ],
        }
        path = self.erp_quote_dir / f"{ext_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return SyncResult(ok=True, external_id=ext_id, message="已写入 ERP 成本同步目录",
                          payload_path=str(path))

    def push_bid_snapshot(self, package: BidPackage, *, project_code: str = "") -> SyncResult:
        self.erp_bid_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext_id = f"ERP-B-{ts}"
        payload = {
            "external_id": ext_id,
            "project_code": project_code or "DEFAULT",
            "product_code": package.product_code,
            "can_bid": package.can_bid,
            "negative_count": package.deviation_table.negative_count,
            "critical_negatives": len(package.deviation_table.critical_negatives),
            "compliance_overall": package.compliance_report.overall.value,
            "matched_qual_count": sum(1 for q in package.matched_qualifications.values() if q),
            "matched_record_count": len(package.matched_records),
        }
        path = self.erp_bid_dir / f"{ext_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return SyncResult(ok=True, external_id=ext_id, message="已写入 ERP 投标快照目录",
                          payload_path=str(path))
