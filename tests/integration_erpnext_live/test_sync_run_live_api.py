# tests/integration_erpnext_live/test_sync_run_live_api.py
import os
import tempfile
import unittest
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app as app_module
from db.session import get_db
from models.base import Base


class TestSyncRunLiveAPI(unittest.TestCase):
    """
    LIVE Integration test:
    - REAL ERPNext connection (no mock)
    - REAL DB (sqlite temp)
    - OpenAI ALWAYS mocked
    - unittest only (no pytest fixtures)
    """

    def setUp(self):
        # --- Require ERPNext env (LIVE) ---
        required = ["ERPNEXT_BASE_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET"]        
        # --- Prevent background scheduler from starting during TestClient startup ---
        # (we test /sync/run explicitly, we don't want the background loop running)
        self._patch_sched_start = patch.object(app_module.scheduler, "start", new=AsyncMock())
        self._patch_sched_stop = patch.object(app_module.scheduler, "stop", new=AsyncMock())
        self._patch_sched_start.start()
        self._patch_sched_stop.start()

        # --- Real DB (sqlite file) ---
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self._tmp.close()

        self.engine = create_engine(
            f"sqlite:///{self._tmp.name}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)

        # --- Override get_db dependency so API uses our test DB ---
        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app_module.app.dependency_overrides[get_db] = override_get_db

        # --- TestClient (do NOT re-raise server exceptions; we assert on HTTP codes) ---
        self.client = TestClient(app_module.app, raise_server_exceptions=False)

        # Ensure cache exists for controllers that expect it
        app_module.app.state.ttl_cache = {}

    def tearDown(self):
        try:
            self.client.close()
        except Exception:
            pass

        app_module.app.dependency_overrides.clear()

        # stop scheduler patches
        try:
            self._patch_sched_start.stop()
            self._patch_sched_stop.stop()
        except Exception:
            pass

        try:
            self.engine.dispose()
        finally:
            try:
                os.unlink(self._tmp.name)
            except Exception:
                pass

    def _mock_openai(self):
        """
        Always mock OpenAI enrichment (even if AI is disabled, this is safe).
        """
        return patch(
            "services.ai_risk.AIRiskClient.analyze_invoice",
            return_value={
                "risk_adjustment": 0.0,
                "extra_reasons": [],
                "supplier_signal": "UNKNOWN",
            },
        )

    def test_sync_run_live_success(self):
        with self._mock_openai():
            r = self.client.post("/sync/run")

        # If ERPNext credentials are valid and reachable -> expect 200
        self.assertEqual(r.status_code, 200, msg=r.text)
        data = r.json().get("data") or {}
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("candidates", data)
        self.assertIn("db_updated", data)
        self.assertIn("risk_recalculated", data)
        self.assertIn("last_modified_before", data)
        self.assertIn("last_modified_after", data)

        # Sanity: invoices endpoint should still respond after sync
        r2 = self.client.get("/invoices?limit=500&include_items=true")
        self.assertEqual(r2.status_code, 200, msg=r2.text)
        self.assertIn("data", r2.json())

    def test_sync_run_live_second_run_is_stable(self):
        """
        Run twice: second run should NOT crash.
        Often it will have fewer (or zero) candidates thanks to last_modified cursor.
        """
        with self._mock_openai():
            r1 = self.client.post("/sync/run")
            self.assertEqual(r1.status_code, 200, msg=r1.text)

            r2 = self.client.post("/sync/run")
            self.assertEqual(r2.status_code, 200, msg=r2.text)

        d2 = r2.json().get("data") or {}
        self.assertEqual(d2.get("status"), "ok")
        self.assertIn("candidates", d2)


if __name__ == "__main__":
    unittest.main()
