import os
import tempfile
import unittest
from unittest.mock import patch

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
                {"idx": 1, "item_code": "Office Supplies", "item_name": "Office Supplies", "qty": 1, "rate": 1200, "amount": 1200}
            ],
        }


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

        # reset cache
        app.state.ttl_cache = {}

        with self.SessionLocal() as db:
            db.query(RiskAnalysis).delete()
            db.query(Invoice).delete()
            db.commit()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        try:
            self.engine.dispose()
        finally:
            if os.path.exists(self._tmp.name):
                os.unlink(self._tmp.name)

    def test_sync_run_success_erp_mocked_openai_mocked(self):
        # Patch the global _sync instance to use fake ERP
        import controllers.sync as sync_controller
        sync_controller._sync.erp = _FakeERP()

        # ALWAYS mock OpenAI (even if AI disabled)
        with patch("services.ai_risk.AIRiskClient.analyze_invoice", return_value={
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }):
            r = self.client.post("/sync/run")
            self.assertEqual(r.status_code, 200)

        data = r.json()["data"]
        self.assertEqual(data["status"], "ok")
        self.assertIn("db_updated", data)
        self.assertIn("risk_recalculated", data)

        # Verify invoice persisted -> /invoices sees it
        r2 = self.client.get("/invoices?limit=50&include_items=true")
        self.assertEqual(r2.status_code, 200)
        invoices = r2.json()["data"]
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["invoice_id"], "ACC-PINV-2026-00001")

    def test_sync_run_cache_optional_branch(self):
        import controllers.sync as sync_controller
        sync_controller._sync.erp = _FakeERP()

        # make cache missing to hit exception branch in controller
        app.state.ttl_cache = None

        with patch("services.ai_risk.AIRiskClient.analyze_invoice", return_value={
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }):
            r = self.client.post("/sync/run")
            self.assertEqual(r.status_code, 200)

        self.assertEqual(r.json()["data"]["status"], "ok")

    def test_sync_run_failure_erp_raises(self):
        import controllers.sync as sync_controller

        class _FailERP:
            async def list_purchase_invoices(self, limit: int = 50):
                raise Exception("ERP down")

            async def get_purchase_invoice(self, name: str):
                raise Exception("ERP down")

        sync_controller._sync.erp = _FailERP()

        with patch("services.ai_risk.AIRiskClient.analyze_invoice", return_value={
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }):
            r = self.client.post("/sync/run")

        # if exception bubbles -> FastAPI returns 500
        self.assertEqual(r.status_code, 500)


if __name__ == "__main__":
    unittest.main()
