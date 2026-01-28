from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from core.config import settings
from db.session import get_db
from helpers import cache_get, cache_set
from queries.risk import list_anomalies
from schemas.responses import ApiResponse
from schemas.risk import RiskOut

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/anomalies", response_model=ApiResponse[list[RiskOut]])
def anomalies(
    min_rate: float = Query(0.6, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """
    DB-driven anomalies list (fast).
    Returns supplier + invoice_id + risk + reasons.
    """
    invoices = list_anomalies(db, min_rate=min_rate, limit=limit)

    out: list[RiskOut] = []
    for inv in invoices:
        if not inv.risk:
            continue
        out.append(
            RiskOut(
                invoice_id=inv.invoice_id,
                supplier=inv.supplier,
                rate=inv.risk.rate,
                risk_level=inv.risk.risk_level,
                reasons=inv.risk.reasons or [],
            )
        )

    return ApiResponse(data=out)


@router.get("/vendors", response_model=ApiResponse[dict])
def vendors_chart(
    request: Request,
    min_rate: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    """
    Vendors chart data for frontend:
    - total invoices per supplier
    - high/critical count (by risk_level)  (from DB)
    Uses internal TTL cache to avoid re-aggregating each refresh.
    """
    cache = request.app.state.ttl_cache
    cache_key = f"vendors:min_rate={min_rate}:limit={limit}"
    cached = cache_get(cache, cache_key)
    if cached is not None:
        return ApiResponse(data=cached)

    # Pull a lot of invoices (DB source of truth)
    # Using existing invoices endpoint query logic would be another option,
    # but here we aggregate from ORM objects quickly.
    from queries.invoices import list_invoices  # local import to avoid circular

    invoices = list_invoices(db, limit=limit)

    by_supplier: dict[str, dict] = {}
    for inv in invoices:
        supplier = inv.supplier or "Unknown"
        if supplier not in by_supplier:
            by_supplier[supplier] = {
                "supplier": supplier,
                "invoices": 0,
                "avg_total": 0.0,
                "high_or_more": 0,
                "critical": 0,
            }

        bucket = by_supplier[supplier]
        bucket["invoices"] += 1

        total = float(inv.grand_total or 0.0)
        bucket["avg_total"] += total

        if inv.risk:
            # Optionally filter by min_rate
            if inv.risk.rate >= min_rate:
                if inv.risk.risk_level in ("HIGH", "CRITICAL"):
                    bucket["high_or_more"] += 1
                if inv.risk.risk_level == "CRITICAL":
                    bucket["critical"] += 1

    # finalize avg_total
    rows = list(by_supplier.values())
    for r in rows:
        if r["invoices"] > 0:
            r["avg_total"] = round(r["avg_total"] / r["invoices"], 2)

    # sort by number of invoices desc
    rows.sort(key=lambda x: x["invoices"], reverse=True)

    data = {
        "rows": rows,
        "meta": {
            "min_rate": min_rate,
            "limit": limit,
        }
    }

    cache_set(cache, cache_key, data, ttl_seconds=settings.DASHBOARD_TTL_SECONDS)
    return ApiResponse(data=data)
