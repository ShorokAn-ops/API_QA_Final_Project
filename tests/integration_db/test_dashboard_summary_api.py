import os
import tempfile
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from db.session import get_db
from models.base import Base
from models.invoice import Invoice
from models.risk import RiskAnalysis


class TestDashboardSummaryAPI(unittest.TestCase):
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
        self.client = TestClient(app)

        # clear cache every test
        app.state.ttl_cache = {}

        # clean db
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

    def _seed(self):
        with self.SessionLocal() as db:
            inv1 = Invoice(invoice_id="INV-1", supplier="A", grand_total=1000, erp_modified="m1")
            inv2 = Invoice(invoice_id="INV-2", supplier="A", grand_total=2000, erp_modified="m2")
            inv3 = Invoice(invoice_id="INV-3", supplier="B", grand_total=3000, erp_modified="m3")
            db.add_all([inv1, inv2, inv3])
            db.flush()

            # inv1 LOW, inv2 CRITICAL, inv3 no risk
            db.add(RiskAnalysis(invoice_id_fk=inv1.id, rate=0.2, risk_level="LOW", reasons=[]))
            db.add(RiskAnalysis(invoice_id_fk=inv2.id, rate=1.0, risk_level="CRITICAL", reasons=[{"reason": "x"}]))
            db.commit()

    def test_dashboard_summary_success(self):
        self._seed()

        r = self.client.get("/dashboard/summary?limit=500")
        self.assertEqual(r.status_code, 200)

        data = r.json()["data"]
        self.assertEqual(data["total_invoices"], 3)
        self.assertEqual(data["total_suppliers"], 2)
        self.assertIn("risk_counts", data)

        # expected: LOW=1, CRITICAL=1, NO_RISK=1
        rc = data["risk_counts"]
        self.assertEqual(rc["LOW"], 1)
        self.assertEqual(rc["CRITICAL"], 1)
        self.assertEqual(rc["NO_RISK"], 1)

    def test_dashboard_summary_empty_db(self):
        r = self.client.get("/dashboard/summary?limit=500")
        self.assertEqual(r.status_code, 200)
        data = r.json()["data"]
        self.assertEqual(data["total_invoices"], 0)
        self.assertEqual(data["total_suppliers"], 0)
        self.assertEqual(data["risk_counts"]["NO_RISK"], 0)

    def test_dashboard_summary_validation_limit_zero(self):
        r = self.client.get("/dashboard/summary?limit=0")
        self.assertEqual(r.status_code, 422)

    def test_dashboard_summary_cache_hit(self):
        self._seed()

        r1 = self.client.get("/dashboard/summary?limit=500")
        self.assertEqual(r1.status_code, 200)
        first = r1.json()["data"]

        # second request should hit cache and match exactly
        r2 = self.client.get("/dashboard/summary?limit=500")
        self.assertEqual(r2.status_code, 200)
        second = r2.json()["data"]

        self.assertEqual(first, second)
        # sanity check: cache key exists
        self.assertTrue(any(k.startswith("summary:") for k in app.state.ttl_cache.keys()))


if __name__ == "__main__":
    unittest.main()
