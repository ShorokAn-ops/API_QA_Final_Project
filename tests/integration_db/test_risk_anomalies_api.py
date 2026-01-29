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


class TestRiskAnomaliesAPI(unittest.TestCase):
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
            inv1 = Invoice(invoice_id="INV-LOW", supplier="S1", grand_total=1000, erp_modified="m1")
            inv2 = Invoice(invoice_id="INV-HIGH", supplier="S2", grand_total=200000, erp_modified="m2")
            db.add_all([inv1, inv2])
            db.flush()

            db.add(RiskAnalysis(invoice_id_fk=inv1.id, rate=0.2, risk_level="LOW", reasons=[]))
            db.add(RiskAnalysis(invoice_id_fk=inv2.id, rate=0.9, risk_level="CRITICAL", reasons=[{"reason": "boom"}]))
            db.commit()

    def test_anomalies_success_filtered(self):
        self._seed()

        r = self.client.get("/risk/anomalies?min_rate=0.6&limit=100")
        self.assertEqual(r.status_code, 200)

        rows = r.json()["data"]
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 1)

        self.assertEqual(rows[0]["invoice_id"], "INV-HIGH")
        self.assertEqual(rows[0]["risk_level"], "CRITICAL")
        self.assertGreaterEqual(rows[0]["rate"], 0.6)

    def test_anomalies_success_empty(self):
        self._seed()

        r = self.client.get("/risk/anomalies?min_rate=0.95&limit=100")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"], [])

    def test_anomalies_validation_min_rate_out_of_range(self):
        r1 = self.client.get("/risk/anomalies?min_rate=-0.1")
        self.assertEqual(r1.status_code, 422)

        r2 = self.client.get("/risk/anomalies?min_rate=1.1")
        self.assertEqual(r2.status_code, 422)

    def test_anomalies_validation_limit_zero(self):
        r = self.client.get("/risk/anomalies?limit=0")
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
