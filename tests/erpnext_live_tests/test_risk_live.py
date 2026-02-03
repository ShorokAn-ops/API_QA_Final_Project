
import os
import unittest

from tests.erpnext_live_tests._live_helpers import (
    create_purchase_invoice_in_erpnext,
    delete_purchase_invoice_in_erpnext,
    run_backend_sync,
    get_risk_anomalies,
    get_risk_vendors,
    recalculate_risk,
)

LIVE_REQUIRED = ["ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET", "BACKEND_BASE_URL", "ERP_SUPPLIER", "ERP_COMPANY", "ERP_ITEM_CODE"]

def _has_live_env() -> bool:
    return all(os.getenv(k) for k in LIVE_REQUIRED)

@unittest.skipUnless(_has_live_env(), "LIVE ERPNext env vars not set (ERP_BASE_URL, ERP_API_KEY, ERP_API_SECRET, BACKEND_BASE_URL, ERP_SUPPLIER, ERP_COMPANY, ERP_ITEM_CODE)")
class TestRiskEndpoints_LiveERPNext(unittest.TestCase):
    def setUp(self):
        self.created_invoice_names = []

    def tearDown(self):
        for name in self.created_invoice_names:
            delete_purchase_invoice_in_erpnext(name)

    def test_anomalies_contains_created_high_risk_invoice_after_recalculate(self):
        """
        We create a 'high risk' style invoice (qty >=30 and rate >=10000 in your rule-based engine),
        then sync + recalculate, and assert it shows in /risk/anomalies (min_rate=0.6).
        """
        supplier = os.environ["ERP_SUPPLIER"]
        company = os.environ["ERP_COMPANY"]
        item_code = os.environ["ERP_ITEM_CODE"]

        inv_name = create_purchase_invoice_in_erpnext(
            supplier=supplier, company=company, item_code=item_code, qty=30.0, rate=10000.0
        )
        self.created_invoice_names.append(inv_name)

        run_backend_sync()
        recalculate_risk(limit=500)

        anomalies = get_risk_anomalies(min_rate=0.6)
        hit = next((x for x in anomalies if x.get("invoice_id") == inv_name), None)
        self.assertIsNotNone(hit, "Expected created invoice to appear in anomalies after sync+recalculate")
        self.assertIn(hit.get("risk_level"), ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(float(hit.get("rate", 0.0)), 0.6)

    def test_vendors_endpoint_contains_supplier_row(self):
        supplier = os.environ["ERP_SUPPLIER"]
        company = os.environ["ERP_COMPANY"]
        item_code = os.environ["ERP_ITEM_CODE"]

        inv_name = create_purchase_invoice_in_erpnext(
            supplier=supplier, company=company, item_code=item_code, qty=1.0, rate=1200.0
        )
        self.created_invoice_names.append(inv_name)

        run_backend_sync()
        recalculate_risk(limit=500)

        vendors = get_risk_vendors(min_rate=0.0)
        rows = vendors.get("rows", [])
        self.assertIsInstance(rows, list)
        self.assertTrue(any(r.get("supplier") == supplier for r in rows), "Supplier should appear in /risk/vendors rows")

if __name__ == "__main__":
    unittest.main()
