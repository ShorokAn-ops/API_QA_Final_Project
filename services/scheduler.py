import asyncio
import logging
from sqlalchemy.orm import Session

from core.config import settings
from db.session import SessionLocal
from services.sync_service import SyncService

log = logging.getLogger("scheduler")


class Scheduler:
    def __init__(self) -> None:
        self.sync = SyncService()
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not settings.SYNC_ENABLED:
            log.info("SYNC_ENABLED=false -> scheduler not started")
            return
        if self._task and not self._task.done():
            return

        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        log.info("Scheduler started (interval=%ss)", settings.SYNC_INTERVAL_SECONDS)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.sleep(0)  # allow loop to exit
            self._task.cancel()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            db: Session = SessionLocal()
            try:
                res = await self.sync.run_one_cycle(db)
                log.info("sync cycle result: %s", res)
            except Exception as e:
                log.exception("sync cycle failed: %s", e)
            finally:
                db.close()

            await asyncio.sleep(max(1, settings.SYNC_INTERVAL_SECONDS))
