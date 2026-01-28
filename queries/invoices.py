from sqlalchemy.orm import Session, joinedload
from models.invoice import Invoice, InvoiceItem


def get_invoice_by_invoice_id(db: Session, invoice_id: str) -> Invoice | None:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items), joinedload(Invoice.risk))
        .filter(Invoice.invoice_id == invoice_id)
        .first()
    )


def list_invoices(db: Session, limit: int = 100) -> list[Invoice]:
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
    inv = db.query(Invoice).filter(Invoice.invoice_id == invoice_id).first()
    if not inv:
        inv = Invoice(invoice_id=invoice_id)
        db.add(inv)
        db.flush()

    inv.supplier = supplier
    inv.posting_date = posting_date
    inv.grand_total = grand_total
    inv.erp_modified = erp_modified
    inv.items_hash = items_hash

    # Replace items safely (simple, clear)
    inv.items.clear()
    for it in items:
        inv.items.append(
            InvoiceItem(
                idx=it.get("idx"),
                item_code=it.get("item_code"),
                item_name=it.get("item_name"),
                qty=it.get("qty"),
                rate=it.get("rate"),
                amount=it.get("amount"),
            )
        )

    db.commit()
    db.refresh(inv)
    return inv
