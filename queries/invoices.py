from sqlalchemy.orm import Session, joinedload
from sqlalchemy import delete

from models.invoice import Invoice, InvoiceItem


def get_invoice_by_invoice_id(db: Session, invoice_id: str) -> Invoice | None:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items), joinedload(Invoice.risk))
        .filter(Invoice.invoice_id == invoice_id)
        .first()
    )




def list_invoices(db: Session, limit: int = 500) -> list[Invoice]:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items), joinedload(Invoice.risk))
        .order_by(Invoice.id.desc())
        .limit(limit)
        .all()
    )


def upsert_invoice_and_items(db: Session, *, invoice_data: dict, items: list[dict]) -> Invoice:
    """
    Upsert invoice + replace its items (safe for UNIQUE constraints).
    invoice_data keys expected:
      invoice_id, supplier, posting_date, grand_total, erp_modified, items_hash
    """

    inv_id = str(invoice_data.get("invoice_id") or "").strip()
    if not inv_id:
        raise ValueError("invoice_data.invoice_id is required")

    inv = db.query(Invoice).filter(Invoice.invoice_id == inv_id).first()
    if inv is None:
        inv = Invoice(invoice_id=inv_id)
        db.add(inv)
        db.flush()  # assign inv.id

    # Update invoice fields
    inv.supplier = invoice_data.get("supplier")
    inv.posting_date = invoice_data.get("posting_date")
    inv.grand_total = float(invoice_data.get("grand_total") or 0.0)
    inv.erp_modified = invoice_data.get("erp_modified")
    inv.items_hash = invoice_data.get("items_hash")

    db.flush()  # ensure inv.id exists

    # Replace items to avoid UNIQUE constraint issues
    db.execute(delete(InvoiceItem).where(InvoiceItem.invoice_id_fk == inv.id))
    db.flush()

    for it in items or []:
        db.add(
            InvoiceItem(
                invoice_id_fk=inv.id,
                idx=int(it.get("idx") or 0),
                item_code=str(it.get("item_code") or ""),
                item_name=str(it.get("item_name") or it.get("item_code") or ""),
                qty=float(it.get("qty") or 0.0),
                rate=float(it.get("rate") or 0.0),
                amount=float(it.get("amount") or 0.0),
            )
        )

    db.commit()

    # Optional: load relationships
    db.refresh(inv)
    return inv
