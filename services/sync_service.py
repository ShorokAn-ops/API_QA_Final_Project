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


from sqlalchemy.orm import Session
from core.logger import log

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
            return {"status": "skipped", "reason": "sync already running"}

        async with self._lock:
            last_modified = get_state(db, SYNC_STATE_KEY)

            try:
                rows = await self.erp.list_purchase_invoices(
                    limit=settings.SYNC_MAX_CHANGED_PER_CYCLE
                )
            except Exception as e:
                db.rollback()
                log.exception("ERP list_purchase_invoices failed: %s", e)
                return {
                    "status": "error",
                    "step": "list_purchase_invoices",
                    "last_modified_before": last_modified,
                    "error": str(e),
                }

            changed: list[dict] = []
            newest_seen = last_modified

            for r in rows or []:
                inv_id = r.get("name")
                erp_mod = r.get("modified")
                if not inv_id:
                    continue

                # track newest modified seen (cursor target)
                if erp_mod and (newest_seen is None or erp_mod > newest_seen):
                    newest_seen = erp_mod

                # delta by last_modified (fast filter)
                if last_modified and erp_mod and erp_mod <= last_modified:
                    continue

                changed.append(
                    {
                        "invoice_id": inv_id,
                        "supplier": r.get("supplier"),
                        "posting_date": r.get("posting_date"),
                        "grand_total": r.get("grand_total"),
                        "modified": erp_mod,
                    }
                )

            updated_count = 0
            recalculated_count = 0
            skipped_same_hash = 0
            failed_invoices: list[str] = []

            for meta in changed:
                inv_id = meta["invoice_id"]

                try:
                    details = await self.erp.get_purchase_invoice(inv_id)
                    raw_items = details.get("items") or []

                    # --- DEDUPE by UNIQUE key (idx, item_code) to prevent IntegrityError ---
                    seen: set[tuple[int, str]] = set()
                    items: list[dict] = []
                    for it in raw_items:
                        idx = int(it.get("idx") or 0)
                        item_code = (it.get("item_code") or "").strip()
                        key = (idx, item_code)
                        if key in seen:
                            continue
                        seen.add(key)
                        items.append(it)

                    h = items_hash(items)

                    existing = get_invoice_by_invoice_id(db, inv_id)
                    if (
                        existing
                        and existing.erp_modified == meta.get("modified")
                        and existing.items_hash == h
                    ):
                        skipped_same_hash += 1
                        continue

                    # Upsert invoice + replace items (your upsert should clear+flush and rollback on error)
                    inv = upsert_invoice_and_items(
                        db,
                        invoice_id=inv_id,
                        supplier=meta.get("supplier"),
                        posting_date=meta.get("posting_date"),
                        grand_total=float(meta.get("grand_total") or 0),
                        erp_modified=meta.get("modified"),
                        items_hash=h,
                        items=items,
                    )
                    updated_count += 1

                    # compute risk only when changed
                    risk = compute_risk(
                        {"grand_total": inv.grand_total},
                        [
                            {
                                "qty": it.qty,
                                "rate": it.rate,
                                "amount": it.amount,
                                "item_code": it.item_code,
                                "item_name": it.item_name,
                                "idx": it.idx,
                            }
                            for it in inv.items
                        ],
                    )

                    upsert_risk(
                        db,
                        invoice_pk=inv.id,
                        rate=risk["rate"],
                        risk_level=risk["risk_level"],
                        reasons=risk["reasons"],
                    )
                    recalculated_count += 1

                except Exception as e:
                    # IMPORTANT: keep session usable for next invoices in same cycle
                    db.rollback()
                    failed_invoices.append(inv_id)
                    log.exception("sync failed for invoice %s: %s", inv_id, e)
                    continue

            # update sync cursor (only if cycle reached the end)
            try:
                if newest_seen and newest_seen != last_modified:
                    set_state(db, SYNC_STATE_KEY, newest_seen)
            except Exception as e:
                db.rollback()
                log.exception("failed updating sync cursor: %s", e)
                return {
                    "status": "error",
                    "step": "update_cursor",
                    "last_modified_before": last_modified,
                    "last_modified_after": newest_seen,
                    "error": str(e),
                }

            return {
                "status": "ok",
                "last_modified_before": last_modified,
                "last_modified_after": newest_seen,
                "candidates": len(changed),
                "db_updated": updated_count,
                "risk_recalculated": recalculated_count,
                "skipped_same_hash": skipped_same_hash,
                "failed_invoices": failed_invoices,
            }