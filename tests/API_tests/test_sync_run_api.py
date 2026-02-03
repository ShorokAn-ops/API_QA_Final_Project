import os
import tempfile
import unittest
import inspect
from unittest.mock import patch, AsyncMock, Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from db.session import get_db
from models.base import Base
from models.invoice import Invoice
from models.risk import RiskAnalysis


class _FakeERP:
    async def list_purchase_invoices(self, limit: int = 50):
        # ERPNext list endpoint returns minimal meta rows
        return [
            {
                "name": "ACC-PINV-2026-00001",
                "supplier": "Atlas Office Supplies",
                "posting_date": "2026-01-22",
                "grand_total": 1200.0,
                "modified": "2026-01-22 04:21:05",
            }
        ]

    async def get_purchase_invoice(self, name: str):
        # ERPNext details endpoint includes items
        return {
            "name": name,
            "items": [
                {
                    "idx": 1,
                    "item_code": "Office Supplies",
                    "item_name": "Office Supplies",
                    "qty": 1,
                    "rate": 1200,
                    "amount": 1200,
                }
            ],
        }


def _patch_openai_analyze_invoice():
    """
    Patch AIRiskClient.analyze_invoice in a way that works whether
    analyze_invoice is async or sync in your code.
    """
    import services.ai_risk as ai_risk_mod

    target = "services.ai_risk.AIRiskClient.analyze_invoice"
    is_async = inspect.iscoroutinefunction(ai_risk_mod.AIRiskClient.analyze_invoice)

    fake_payload = {
        "risk_adjustment": 0.0,
        "extra_reasons": [],
        "supplier_signal": "UNKNOWN",
    }

    if is_async:
        return patch(target, new=AsyncMock(return_value=fake_payload))
    return patch(target, new=Mock(return_value=fake_payload))


class TestSyncRunAPI(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self._tmp.close()

        self.engine = create_engine(
            f"sqlite:///{self._tmp.name}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, future=True)
        Base.metadata.create_all(bind=self.engine)

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app, raise_server_exceptions=False)

        # reset cache to a plain dict (works with .keys()).
        app.state.ttl_cache = {}

        # Clean DB tables
        with self.SessionLocal() as db:
            db.query(RiskAnalysis).delete()
            db.query(Invoice).delete()
            db.commit()

        # Ensure controller uses fake ERP by default for tests
        import controllers.sync as sync_controller
        sync_controller._sync.erp = _FakeERP()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        try:
            self.engine.dispose()
        finally:
            if os.path.exists(self._tmp.name):
                os.unlink(self._tmp.name)

    def test_sync_run_success_erp_mocked_openai_mocked(self):
        with _patch_openai_analyze_invoice():
            r = self.client.post("/sync/run")
            self.assertEqual(r.status_code, 200)

        payload = r.json()
        self.assertIn("data", payload)
        data = payload["data"]

        # Your service returns these keys (as in your existing assertions)
        self.assertEqual(data.get("status"), "ok")
        self.assertIn("db_updated", data)
        self.assertIn("risk_recalculated", data)

        # Verify invoice persisted -> /invoices sees it
        r2 = self.client.get("/invoices?limit=50&include_items=true")
        self.assertEqual(r2.status_code, 200)
        invoices = r2.json()["data"]
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["invoice_id"], "ACC-PINV-2026-00001")

    def test_sync_run_failure_erp_raises(self):
        import controllers.sync as sync_controller

        class _FailERP:
            async def list_purchase_invoices(self, limit: int = 50):
                raise Exception("ERP down")

            async def get_purchase_invoice(self, name: str):
                raise Exception("ERP down")

        sync_controller._sync.erp = _FailERP()

        with _patch_openai_analyze_invoice():
            r = self.client.post("/sync/run")

        # If exception bubbles -> FastAPI returns 500
        self.assertEqual(r.status_code, 500)

    # -------------------------
    # Cache behavior (vendors: prefix invalidation)
    # -------------------------

    def test_sync_run_cache_clears_vendors_prefix_and_returns_cleared_keys(self):
        """
        Endpoint tries to clear TTL cached dashboard endpoints with prefix 'vendors:'.
        We seed the cache with vendors:* keys, run sync, and assert they're cleared
        and the response includes ttl_cache_cleared_keys.
        """
        # Seed cache with some keys
        app.state.ttl_cache = {
            "vendors:top": {"dummy": 1},
            "vendors:analytics": {"dummy": 2},
            "summary:main": {"dummy": 3},  # should NOT be cleared by vendors:
        }

        with _patch_openai_analyze_invoice():
            r = self.client.post("/sync/run")
            self.assertEqual(r.status_code, 200)

        data = r.json()["data"]
        self.assertEqual(data.get("status"), "ok")

        # It should include the cleared keys list/count (depends on your helper)
        # We only assert it exists and looks like "something cleared".
        self.assertIn("ttl_cache_cleared_keys", data)

        # After clearing vendors:, those keys should be gone from cache
        self.assertFalse(any(k.startswith("vendors:") for k in app.state.ttl_cache.keys()))
        # But other prefixes remain
        self.assertTrue(any(k.startswith("summary:") for k in app.state.ttl_cache.keys()))

    def test_sync_run_cache_optional_branch_cache_missing_does_not_break(self):
        """
        Controller treats cache as optional; if cache access fails it should still return 200.
        """
        # Force the optional-cache exception branch
        app.state.ttl_cache = None

        with _patch_openai_analyze_invoice():
            r = self.client.post("/sync/run")
            self.assertEqual(r.status_code, 200)

        self.assertEqual(r.json()["data"].get("status"), "ok")

    # -------------------------
    # API contract / validation
    # -------------------------

    def test_sync_run_method_not_allowed_get(self):
        """
        /sync/run is POST-only. GET should return 405.
        """
        r = self.client.get("/sync/run")
        self.assertEqual(r.status_code, 405)


if __name__ == "__main__":
    unittest.main()
