import os
import tempfile
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from db.session import get_db
from models.base import Base
from models.invoice import Invoice, InvoiceItem


class TestInvoicesAPI(unittest.TestCase):
    def setUp(self):
        # --- Real DB (sqlite file) ---
        self._tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self._tmp.close()

        self.engine = create_engine(
            f"sqlite:///{self._tmp.name}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False, future=True)
        Base.metadata.create_all(bind=self.engine)

        # override FastAPI dependency: get_db()
        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

        # clean state each test
        with self.SessionLocal() as db:
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

    def _seed_invoice_with_items(self):
        with self.SessionLocal() as db:
            inv = Invoice(
                invoice_id="ACC-PINV-2026-00001",
                supplier="Atlas Office Supplies",
                posting_date="2026-01-22",
                grand_total=1200.0,
                erp_modified="2026-01-22 04:21:05",
                items_hash="hash1",
            )
            db.add(inv)
            db.flush()

            db.add_all([
                InvoiceItem(
                    invoice_id_fk=inv.id,
                    idx=1,
                    item_code="Office Supplies",
                    item_name="Office Supplies",
                    qty=1.0,
                    rate=1200.0,
                    amount=1200.0,
                ),
                InvoiceItem(
                    invoice_id_fk=inv.id,
                    idx=2,
                    item_code="Paper",
                    item_name="Paper",
                    qty=2.0,
                    rate=10.0,
                    amount=20.0,
                ),
            ])
            db.commit()

    def test_get_invoices_success_include_items_true(self):
        self._seed_invoice_with_items()

        r = self.client.get("/invoices?limit=100&include_items=true")
        self.assertEqual(r.status_code, 200)

        body = r.json()
        self.assertIn("data", body)
        self.assertIsInstance(body["data"], list)
        self.assertEqual(len(body["data"]), 1)

        inv = body["data"][0]
        self.assertEqual(inv["invoice_id"], "ACC-PINV-2026-00001")
        self.assertEqual(inv["supplier"], "Atlas Office Supplies")
        self.assertIsInstance(inv["items"], list)
        self.assertEqual(len(inv["items"]), 2)

    def test_get_invoices_success_include_items_false(self):
        self._seed_invoice_with_items()

        r = self.client.get("/invoices?limit=100&include_items=false")
        self.assertEqual(r.status_code, 200)

        inv = r.json()["data"][0]
        # controller returns [] when include_items=false
        self.assertEqual(inv["items"], [])

    def test_get_invoices_success_empty_db(self):
        r = self.client.get("/invoices?limit=10&include_items=true")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["data"], [])

    def test_get_invoices_validation_limit_zero(self):
        r = self.client.get("/invoices?limit=0")
        # FastAPI Query(ge=1) => 422
        self.assertEqual(r.status_code, 422)

    def test_get_invoices_validation_limit_too_high(self):
        r = self.client.get("/invoices?limit=501")
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()
