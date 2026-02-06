from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.config import settings
from db.session import get_db
from helpers import cache_get, cache_set
from schemas.responses import ApiResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/summary", response_model=ApiResponse[dict])
def dashboard_summary(
    request: Request,
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """
    Dashboard summary (DB-driven):
    - counts by risk_level
    - total invoices
    - total suppliers
    Uses TTL cache to avoid recomputing often.
    """
    cache = request.app.state.ttl_cache
    cache_key = f"summary:limit={limit}"
    cached = cache_get(cache, cache_key)
    if cached is not None:
        return ApiResponse(data=cached)

    from queries.invoices import list_invoices  # local import

    invoices = list_invoices(db, limit=limit)

    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0, "NO_RISK": 0}
    suppliers = set()

    for inv in invoices:
        if inv.supplier:
            suppliers.add(inv.supplier)

        if inv.risk:
            lvl = inv.risk.risk_level or "NO_RISK"
            risk_counts[lvl] = risk_counts.get(lvl, 0) + 1
        else:
            risk_counts["NO_RISK"] += 1

    data = {
        "total_invoices": len(invoices),
        "total_suppliers": len(suppliers),
        "risk_counts": risk_counts,
        "meta": {"limit": limit},
    }

    cache_set(cache, cache_key, data, ttl_seconds=settings.DASHBOARD_TTL_SECONDS)
    return ApiResponse(data=data)
