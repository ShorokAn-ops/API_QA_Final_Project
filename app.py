from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.logging import setup_logging
from core.config import settings
from db.session import engine
from models.base import Base

# Import all models to register them with SQLAlchemy BEFORE any queries
from models.invoice import Invoice, InvoiceItem
from models.risk import RiskAnalysis
from models.sync_state import SyncState

from controllers.dashboard import router as dashboard_router
from controllers.health import router as health_router
from controllers.invoices import router as invoices_router
from controllers.risk import router as risk_router
from controllers.sync import router as sync_router

from services.sync_service import SyncService
from services.scheduler import Scheduler


setup_logging()

app = FastAPI(title="ERPNext Risk Analyzer (DB + Sync + TTL)")

# --- CORS middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
         "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- DB tables ---
Base.metadata.create_all(bind=engine)

# --- Routers ---
app.include_router(dashboard_router)
app.include_router(health_router)
app.include_router(invoices_router)
app.include_router(risk_router)
app.include_router(sync_router)

# --- Internal TTL cache store (in-memory) ---
# Controllers/services can use: from helpers import cache_get/cache_set
app.state.ttl_cache = {}  # dict[str, (expires_at, data)]

sync_service = SyncService()
scheduler = Scheduler(sync_service)

@app.on_event("startup")
async def on_startup():
    # Start background sync loop (delta by modified) if enabled
    await scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    await scheduler.stop()
