from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.logging import setup_logging
from core.config import settings
from db.session import engine
from models.base import Base

from controllers.dashboard import router as dashboard_router
from controllers.health import router as health_router
from controllers.invoices import router as invoices_router
from controllers.risk import router as risk_router
from controllers.sync import router as sync_router
from controllers.test import router as test_router

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
        "https://untrusted-cythia-unpunctilious.ngrok-free.dev",
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
app.include_router(test_router)

# --- Internal TTL cache store (in-memory) ---
# Controllers/services can use: from helpers import cache_get/cache_set
app.state.ttl_cache = {}  # dict[str, (expires_at, data)]

scheduler = Scheduler()


@app.on_event("startup")
async def on_startup():
    # Start background sync loop (delta by modified) if enabled
    await scheduler.start()


@app.on_event("shutdown")
async def on_shutdown():
    await scheduler.stop()
