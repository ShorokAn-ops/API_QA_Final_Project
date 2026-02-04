from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from db.session import get_db
from queries.invoices import list_invoices
from schemas.responses import ApiResponse
from schemas.invoice import InvoiceOut, InvoiceItemOut, RiskAnalysisOut

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.get("", response_model=ApiResponse[list[InvoiceOut]])
def get_invoices(
    limit: int = Query(500, ge=1, le=500),
    include_items: bool = Query(True),
    db: Session = Depends(get_db),
):
    """
    Returns invoices from DB (source of truth).
    include_items=true includes qty/rate for each item (needed for UI).
    """
    rows = list_invoices(db, limit=limit)

    out: list[InvoiceOut] = []
    for inv in rows:
        items_out = []
        if include_items:
            items_out = [
                InvoiceItemOut(
                    item_code=i.item_code,
                    item_name=i.item_name,
                    qty=i.qty,
                    rate=i.rate,
                    amount=i.amount,
                )
                for i in (inv.items or [])
            ]

        # Serialize risk data if present
        risk_out = None
        if inv.risk:
            risk_out = RiskAnalysisOut(
                rate=inv.risk.rate,
                risk_level=inv.risk.risk_level,
                reasons=inv.risk.reasons if isinstance(inv.risk.reasons, list) else [],
            )

        out.append(
            InvoiceOut(
                invoice_id=inv.invoice_id,
                supplier=inv.supplier,
                posting_date=inv.posting_date,
                grand_total=inv.grand_total,
                erp_modified=inv.erp_modified,
                items=items_out,
                risk=risk_out,
            )
        )

    return ApiResponse(data=out)
