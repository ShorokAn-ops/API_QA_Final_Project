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
from models.invoice import Invoice, InvoiceItem
from models.risk import RiskAnalysis


class TestRiskVendorsAndRecalculateAPI(unittest.TestCase):
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

        # reset cache
        app.state.ttl_cache = {}

        with self.SessionLocal() as db:
            db.query(RiskAnalysis).delete()
            db.query(InvoiceItem).delete()
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
            inv1 = Invoice(invoice_id="INV-1", supplier="VendorA", grand_total=1000, erp_modified="m1")
            inv2 = Invoice(invoice_id="INV-2", supplier="VendorA", grand_total=250000, erp_modified="m2")
            inv3 = Invoice(invoice_id="INV-3", supplier="VendorB", grand_total=5000, erp_modified="m3")
            db.add_all([inv1, inv2, inv3])
            db.flush()

            # items so recalculate has input
            db.add_all([
                InvoiceItem(invoice_id_fk=inv1.id, idx=1, item_code="X", item_name="X", qty=1, rate=1000, amount=1000),
                InvoiceItem(invoice_id_fk=inv2.id, idx=1, item_code="Y", item_name="Y", qty=30, rate=10000, amount=300000),
                InvoiceItem(invoice_id_fk=inv3.id, idx=1, item_code="Z", item_name="Z", qty=2, rate=2500, amount=5000),
            ])

            # existing risk:
            db.add(RiskAnalysis(invoice_id_fk=inv1.id, rate=0.2, risk_level="LOW", reasons=[]))
            db.add(RiskAnalysis(invoice_id_fk=inv2.id, rate=1.0, risk_level="CRITICAL", reasons=[{"reason": "old"}]))
            # inv3 no risk
            db.commit()

    def test_vendors_success_and_cache(self):
        self._seed()

        r1 = self.client.get("/risk/vendors?min_rate=0.0&limit=500")
        self.assertEqual(r1.status_code, 200)

        data1 = r1.json()["data"]
        self.assertIn("rows", data1)
        self.assertIsInstance(data1["rows"], list)
        self.assertGreaterEqual(len(data1["rows"]), 2)

        # cache key exists
        self.assertTrue(any(k.startswith("vendors:") for k in app.state.ttl_cache.keys()))

        # second request should hit cache & match
        r2 = self.client.get("/risk/vendors?min_rate=0.0&limit=500")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["data"], data1)

    def test_vendors_filter_min_rate(self):
        self._seed()

        # min_rate filters counting of high/critical in bucket
        r = self.client.get("/risk/vendors?min_rate=0.9&limit=500")
        self.assertEqual(r.status_code, 200)
        rows = r.json()["data"]["rows"]

        # VendorA has a CRITICAL invoice rate=1.0 so should show high_or_more >=1
        vendor_a = next((x for x in rows if x["supplier"] == "VendorA"), None)
        self.assertIsNotNone(vendor_a)
        self.assertGreaterEqual(vendor_a["high_or_more"], 1)

    def test_vendors_validation(self):
        self.assertEqual(self.client.get("/risk/vendors?min_rate=-0.1").status_code, 422)
        self.assertEqual(self.client.get("/risk/vendors?min_rate=1.1").status_code, 422)
        self.assertEqual(self.client.get("/risk/vendors?limit=0").status_code, 422)

    def test_recalculate_success_clears_cache_and_updates(self):
        self._seed()

        # put something in cache to be cleared
        app.state.ttl_cache["vendors:dummy"] = (9999999999.0, {"x": 1})

        # ALWAYS mock OpenAI enrichment (even if AI disabled)
        with patch("services.ai_risk.AIRiskClient.analyze_invoice", return_value={
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }):
            r = self.client.post("/risk/recalculate?limit=500")
            self.assertEqual(r.status_code, 200)

        out = r.json()["data"]
        self.assertEqual(out["status"], "ok")
        self.assertGreaterEqual(out["recalculated"], 1)
        self.assertIn("ttl_cache_cleared_keys", out)
        self.assertGreaterEqual(out["ttl_cache_cleared_keys"], 1)

        # verify risks exist for invoices after recalc (inv3 should get some computed risk (maybe LOW))
        with self.SessionLocal() as db:
            inv3 = db.query(Invoice).filter_by(invoice_id="INV-3").first()
            self.assertIsNotNone(inv3)
            self.assertIsNotNone(inv3.risk)

    def test_recalculate_cache_optional_branch(self):
        self._seed()

        # remove cache store to force exception branch in controller
        app.state.ttl_cache = None

        with patch("services.ai_risk.AIRiskClient.analyze_invoice", return_value={
            "risk_adjustment": 0.0,
            "extra_reasons": [],
            "supplier_signal": "UNKNOWN",
        }):
            r = self.client.post("/risk/recalculate?limit=500")
            self.assertEqual(r.status_code, 200)

        # controller should not crash even if cache missing
        self.assertEqual(r.json()["data"]["status"], "ok")

    def test_recalculate_validation_limit_zero(self):
        r = self.client.post("/risk/recalculate?limit=0")
        self.assertEqual(r.status_code, 422)

    def test_recalculate_validation_limit_negative(self):
        r = self.client.post("/risk/recalculate?limit=-5")
        self.assertEqual(r.status_code, 422)

    def test_recalculate_validation_limit_too_high(self):
        # NOTE: /risk/recalculate enforces le=2000 in risk.py
        r = self.client.post("/risk/recalculate?limit=2001")
        self.assertEqual(r.status_code, 422)

    def test_recalculate_validation_limit_not_int(self):
        r = self.client.post("/risk/recalculate?limit=abc")
        self.assertEqual(r.status_code, 422)

if __name__ == "__main__":
    unittest.main()
