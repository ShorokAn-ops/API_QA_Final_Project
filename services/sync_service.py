import asyncio
import logging
from sqlalchemy.orm import Session

from core.config import settings
from services.erp_client import ERPClient
from services.hasher import items_hash
from services.risk_engine import compute_risk

from queries.sync_state import get_state, set_state
from queries.invoices import get_invoice_by_invoice_id, upsert_invoice_and_items
from queries.risk import upsert_risk

log = logging.getLogger("sync")


SYNC_STATE_KEY = "purchase_invoice_last_modified"


class SyncService:
    def __init__(self) -> None:
        self.erp = ERPClient()
        self._lock = asyncio.Lock()

    async def run_one_cycle(self, db: Session) -> dict:
        """
        Cycle rule:
        - bring latest invoices list
        - choose changed invoices using last_modified + DB compare
        - fetch invoice details only for changed ones
        - upsert DB + compute risk only if changed
        """
        if self._lock.locked():
            # Prevent parallel sync => avoids infinite loop / dogpile
            return {"status": "skipped", "reason": "sync already running"}

        async with self._lock:
            last_modified = get_state(db, SYNC_STATE_KEY)

            rows = await self.erp.list_purchase_invoices(limit=settings.SYNC_MAX_CHANGED_PER_CYCLE)

            changed = []
            newest_seen = last_modified

            for r in rows:
                inv_id = r.get("name")
                erp_mod = r.get("modified")
                if not inv_id:
                    continue

                # track newest modified seen
                if erp_mod and (newest_seen is None or erp_mod > newest_seen):
                    newest_seen = erp_mod

                # delta by last_modified (fast filter)
                if last_modified and erp_mod and erp_mod <= last_modified:
                    continue

                changed.append({
                    "invoice_id": inv_id,
                    "supplier": r.get("supplier"),
                    "posting_date": r.get("posting_date"),
                    "grand_total": r.get("grand_total"),
                    "modified": erp_mod,
                })

            updated_count = 0
            recalculated_count = 0

            for meta in changed:
                inv_id = meta["invoice_id"]
                details = await self.erp.get_purchase_invoice(inv_id)
                items = details.get("items") or []

                h = items_hash(items)

                existing = get_invoice_by_invoice_id(db, inv_id)
                if existing and existing.erp_modified == meta["modified"] and existing.items_hash == h:
                    # no real change => do nothing
                    continue

                invoice_data = {
                    "invoice_id": inv_id,
                    "supplier": meta.get("supplier"),
                    "posting_date": meta.get("posting_date"),
                    "grand_total": float(meta.get("grand_total") or 0),
                    "erp_modified": meta.get("modified"),
                    "items_hash": h,
                }

                inv = upsert_invoice_and_items(db, invoice_data=invoice_data, items=items)

                updated_count += 1

                # compute risk only when changed
                risk = compute_risk(
                    {"grand_total": inv.grand_total},
                    [{"qty": it.qty, "rate": it.rate, "amount": it.amount, "item_code": it.item_code, "item_name": it.item_name, "idx": it.idx} for it in inv.items],
                )
                upsert_risk(
                    db,
                    invoice_pk=inv.id,
                    rate=risk["rate"],
                    risk_level=risk["risk_level"],
                    reasons=risk["reasons"],
                )
                recalculated_count += 1

            # update sync cursor
            if newest_seen and newest_seen != last_modified:
                set_state(db, SYNC_STATE_KEY, newest_seen)

            return {
                "status": "ok",
                "last_modified_before": last_modified,
                "last_modified_after": newest_seen,
                "candidates": len(changed),
                "db_updated": updated_count,
                "risk_recalculated": recalculated_count,
            }
