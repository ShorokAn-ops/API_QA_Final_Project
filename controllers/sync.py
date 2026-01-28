from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from db.session import get_db
from services.sync_service import SyncService
from schemas.responses import ApiResponse
from helpers import cache_clear_prefix

router = APIRouter(prefix="/sync", tags=["sync"])

_sync = SyncService()


@router.post("/run", response_model=ApiResponse[dict])
async def run_sync(request: Request, db: Session = Depends(get_db)):
    """
    Run one sync cycle manually.
    After sync, we clear TTL cached dashboard endpoints (vendors etc.)
    """
    res = await _sync.run_one_cycle(db)

    # Invalidate cached charts/summary after sync
    try:
        cache = request.app.state.ttl_cache
        cleared = cache_clear_prefix(cache, "vendors:")
        res["ttl_cache_cleared_keys"] = cleared
    except Exception:
        # Cache is optional; don't break sync response
        pass

    return ApiResponse(data=res)
