
import os
import unittest

from tests.erpnext_live_tests._live_helpers import (
    create_purchase_invoice_in_erpnext,
    delete_purchase_invoice_in_erpnext,
    run_backend_sync,
    wait_until_invoice_visible,
)

LIVE_REQUIRED = ["ERP_BASE_URL", "ERP_API_KEY", "ERP_API_SECRET", "BACKEND_BASE_URL", "ERP_SUPPLIER", "ERP_COMPANY", "ERP_ITEM_CODE"]

def _has_live_env() -> bool:
    return all(os.getenv(k) for k in LIVE_REQUIRED)

@unittest.skipUnless(_has_live_env(), "LIVE ERPNext env vars not set (ERP_BASE_URL, ERP_API_KEY, ERP_API_SECRET, BACKEND_BASE_URL, ERP_SUPPLIER, ERP_COMPANY, ERP_ITEM_CODE)")
class TestInvoicesAPI_LiveERPNext(unittest.TestCase):
    def setUp(self):
        self.created_invoice_name = None

    def tearDown(self):
        if self.created_invoice_name:
            delete_purchase_invoice_in_erpnext(self.created_invoice_name)

    def test_invoice_flows_from_erpnext_to_backend_invoices_include_items_true(self):
        supplier = os.environ["ERP_SUPPLIER"]
        company = os.environ["ERP_COMPANY"]
        item_code = os.environ["ERP_ITEM_CODE"]

        # Create in ERPNext
        self.created_invoice_name = create_purchase_invoice_in_erpnext(
            supplier=supplier, company=company, item_code=item_code, qty=1.0, rate=1200.0
        )

        # Trigger backend to pull from ERPNext
        run_backend_sync()

        # Assert it shows in backend /invoices
        inv = wait_until_invoice_visible(self.created_invoice_name, include_items=True)
        self.assertEqual(inv["invoice_id"], self.created_invoice_name)
        self.assertEqual(inv["supplier"], supplier)
        self.assertIsInstance(inv.get("items"), list)
        self.assertGreaterEqual(len(inv["items"]), 1)

    def test_invoice_flows_from_erpnext_to_backend_invoices_include_items_false(self):
        supplier = os.environ["ERP_SUPPLIER"]
        company = os.environ["ERP_COMPANY"]
        item_code = os.environ["ERP_ITEM_CODE"]

        self.created_invoice_name = create_purchase_invoice_in_erpnext(
            supplier=supplier, company=company, item_code=item_code, qty=2.0, rate=10.0
        )

        run_backend_sync()

        inv = wait_until_invoice_visible(self.created_invoice_name, include_items=False)
        self.assertEqual(inv["invoice_id"], self.created_invoice_name)
        # your controller returns [] when include_items=false
        self.assertEqual(inv.get("items"), [])

if __name__ == "__main__":
    unittest.main()
