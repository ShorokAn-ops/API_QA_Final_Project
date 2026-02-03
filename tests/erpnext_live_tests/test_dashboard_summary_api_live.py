import os
import time
import unittest

from tests.erpnext_live_tests._live_helpers import (
    create_purchase_invoice_in_erpnext,
    delete_purchase_invoice_in_erpnext,
    run_backend_sync,
    get_dashboard_summary,
)

LIVE_REQUIRED = [
    "ERP_BASE_URL",
    "ERP_API_KEY",
    "ERP_API_SECRET",
    "BACKEND_BASE_URL",
    "ERP_SUPPLIER",
    "ERP_COMPANY",
    "ERP_ITEM_CODE",
]

def _has_live_env() -> bool:
    return all(os.getenv(k) for k in LIVE_REQUIRED)

def _unwrap_data(payload):
    """
    Your helpers sometimes return:
      {"data": {...}, "error": None}
    This unwraps to the inner data.
    """
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], dict):
        return payload["data"]
    return payload

@unittest.skipUnless(
    _has_live_env(),
    "LIVE ERPNext env vars not set (ERP_BASE_URL, ERP_API_KEY, ERP_API_SECRET, BACKEND_BASE_URL, ERP_SUPPLIER, ERP_COMPANY, ERP_ITEM_CODE)",
)
class TestDashboardSummaryAPI_LiveERPNext(unittest.TestCase):
    def setUp(self):
        self.created_invoice_names = []

    def tearDown(self):
        for name in self.created_invoice_names:
            try:
                delete_purchase_invoice_in_erpnext(name)
            except Exception:
                pass

    def test_dashboard_summary_after_sync_contract(self):
        """
        LIVE test (stable):
        - Create invoice in ERPNext
        - Trigger backend sync (retry until db_updated>=1)
        - Validate /dashboard/summary contract (keys + types)
        NOTE: We DO NOT assert total_invoices increments, because dashboard counters
              can be eventually consistent (cache/aggregation).
        """
        supplier = os.environ["ERP_SUPPLIER"]
        company = os.environ["ERP_COMPANY"]
        item_code = os.environ["ERP_ITEM_CODE"]

        # 1) Create invoice in ERPNext
        inv_name = create_purchase_invoice_in_erpnext(
            supplier=supplier,
            company=company,
            item_code=item_code,
            qty=1.0,
            rate=50.0,
        )
        self.created_invoice_names.append(inv_name)

        # 2) Run backend sync with retries (timing can cause 0 candidates on first cycle)
        db_updated = 0
        last_sync_res = None

        for _ in range(5):
            last_sync_res = run_backend_sync()
            sync_data = _unwrap_data(last_sync_res)
            db_updated = int(sync_data.get("db_updated", 0) or 0)

            if db_updated >= 1:
                break

            time.sleep(2)

        self.assertGreaterEqual(
            db_updated,
            1,
            f"Sync did not update DB after retries. Last sync response: {last_sync_res}",
        )

        # 3) Validate dashboard contract (unwrap {"data": {...}, "error": None})
        summary_resp = get_dashboard_summary()
        summary = _unwrap_data(summary_resp)

        # Required keys
        self.assertIn("total_invoices", summary)
        self.assertIn("total_suppliers", summary)
        self.assertIn("risk_counts", summary)

        # Types
        self.assertIsInstance(summary["total_invoices"], int)
        self.assertIsInstance(summary["total_suppliers"], int)
        self.assertIsInstance(summary["risk_counts"], dict)

        # risk_counts keys (be flexible: depends on your backend)
        for k, v in summary["risk_counts"].items():
            self.assertIsInstance(k, str)
            self.assertIsInstance(v, int)

if __name__ == "__main__":
    unittest.main()
