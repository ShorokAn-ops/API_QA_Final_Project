from sqlalchemy.orm import Session, joinedload
from models.invoice import Invoice, InvoiceItem


def get_invoice_by_invoice_id(db: Session, invoice_id: str) -> Invoice | None:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items), joinedload(Invoice.risk))
        .filter(Invoice.invoice_id == invoice_id)
        .first()
    )


def list_invoices(db: Session, limit: int = 300) -> list[Invoice]:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items), joinedload(Invoice.risk))
        .order_by(Invoice.id.desc())
        .limit(limit)
        .all()
    )

def upsert_invoice_and_items(
    db: Session,
    *,
    invoice_id: str,
    supplier: str | None,
    posting_date: str | None,
    grand_total: float | None,
    erp_modified: str | None,
    items_hash: str | None,
    items: list[dict],
) -> Invoice:
    try:
        inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
        if not inv:
            inv = Invoice(invoice_id=invoice_id)
            db.add(inv)
            db.flush()  # ensures inv.id exists

        inv.supplier = supplier
        inv.posting_date = posting_date
        inv.grand_total = grand_total
        inv.erp_modified = erp_modified
        inv.items_hash = items_hash

        # 1) remove previous items
        inv.items.clear()
        db.flush()  # ✅ force DELETEs before inserting new rows (important for sqlite)

        # 2) de-duplicate incoming items by the UNIQUE key: (idx, item_code)
        seen: set[tuple[int, str]] = set()

        for it in (items or []):
            idx = int(it.get("idx") or 0)
            item_code = (it.get("item_code") or "").strip()

            # if item_code is empty, it can still collide; keep it as empty string
            key = (idx, item_code)

            if key in seen:
                # skip duplicates coming from ERPNext payload
                continue
            seen.add(key)

            inv.items.append(
                InvoiceItem(
                    idx=idx if idx != 0 else None,
                    item_code=item_code or None,
                    item_name=(it.get("item_name") or "").strip() or None,
                    qty=float(it.get("qty") or 0),
                    rate=float(it.get("rate") or 0),
                    amount=float(it.get("amount") or 0),
                )
            )

        db.commit()
        db.refresh(inv)
        return inv

    except Exception:
        db.rollback()
        raise