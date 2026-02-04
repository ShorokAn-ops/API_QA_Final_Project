import asyncio
from contextlib import suppress

from core.config import settings
from core.logger import log 

from sqlalchemy.orm import Session

from db.session import SessionLocal  # או איך שאת יוצרת DB session


class Scheduler:
    def __init__(self, sync_service) -> None:
        self.sync = sync_service
        self._task = None
        self._stop = asyncio.Event()


    async def start(self) -> None:
        """
        Starts background sync loop if enabled.
        Safe to call multiple times; will not start a second loop if one is already running.
        """

        # Log the actual value (helps debug .env parsing issues)
        log.info("SYNC_ENABLED value = %s", settings.SYNC_ENABLED)

        # If disabled -> do nothing (but be explicit in logs)
        if not settings.SYNC_ENABLED:
            log.info("SYNC_ENABLED=false -> scheduler not started")
            return

        # Prevent double-start
        if self._task and not self._task.done():
            log.info("Scheduler already running; start() ignored")
            return

        # Validate / normalize interval (avoid 0/negative causing tight loop)
        interval = getattr(settings, "SYNC_INTERVAL_SECONDS", 5)
        try:
            interval = int(interval)
        except Exception:
            interval = 5

        if interval < 1:
            log.warning("Invalid SYNC_INTERVAL_SECONDS=%s; using 5 seconds", interval)
            interval = 5

        # Reset stop flag and spawn loop
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="sync_scheduler_loop")

        log.info("Scheduler started (interval=%ss)", interval)

    async def stop(self) -> None:
        """Stops background loop gracefully."""
        if not self._task or self._task.done():
            return

        self._stop.set()
        self._task.cancel()

        with suppress(asyncio.CancelledError):
            await self._task

        log.info("Scheduler stopped")

    async def _loop(self) -> None:
        # Normalize interval once for stability
        interval = getattr(settings, "SYNC_INTERVAL_SECONDS", 5)
        try:
            interval = int(interval)
        except Exception:
            interval = 5

        if interval < 1:
            log.warning("Invalid SYNC_INTERVAL_SECONDS=%s; using 5 seconds", interval)
            interval = 5

        log.info("Scheduler loop running (interval=%ss)", interval)

        try:
            while not self._stop.is_set():
                db: Session = SessionLocal()
                try:
                    res = await self.sync.run_one_cycle(db)
                    log.info("sync cycle result: %s", res)

                except asyncio.CancelledError:
                    # If we're being stopped during a DB transaction, rollback & re-raise
                    db.rollback()
                    raise

                except Exception as e:
                    # ✅ CRITICAL: after commit/flush failure, session must rollback
                    db.rollback()
                    log.exception("sync cycle failed: %s", e)

                finally:
                    db.close()

                # Wait for either stop signal OR interval timeout (fast shutdown)
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=interval)

        except asyncio.CancelledError:
            # Normal during shutdown/stop()
            log.info("Scheduler loop cancelled")
            raise

        finally:
            log.info("Scheduler loop exited")