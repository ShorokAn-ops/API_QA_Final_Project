
import os
import time
import requests
from typing import Any, Dict, Optional
import time

DEFAULT_TIMEOUT = float(os.getenv("LIVE_HTTP_TIMEOUT", "30"))
BACKEND_BASE_URL = os.environ["BACKEND_BASE_URL"].rstrip("/")
ERP_BASE_URL = os.environ["ERP_BASE_URL"].rstrip("/")

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val

def erp_headers() -> Dict[str, str]:
    key = _require_env("ERP_API_KEY")
    secret = _require_env("ERP_API_SECRET")
    return {
        "Authorization": f"token {key}:{secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def erp_base_url() -> str:
    return _require_env("ERP_BASE_URL").rstrip("/")

def backend_base_url() -> str:
    # Your FastAPI service that talks to ERPNext
    return _require_env("BACKEND_BASE_URL").rstrip("/")

def _post(url: str, *, headers: Dict[str,str], json_body: Dict[str,Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str,Any]:
    headers = dict(headers)
    # Rarely helps if some proxy reacts to Expect header (safe to set)
    headers.setdefault("Expect", "")

    r = requests.post(url, headers=headers, json=json_body, timeout=timeout)

    if r.status_code >= 400:
        # Try to show ERPNext/Frappe validation message
        try:
            payload = r.json()
        except Exception:
            payload = {"raw": r.text}

        raise RuntimeError(
            f"ERPNext POST failed\n"
            f"URL: {url}\n"
            f"HTTP: {r.status_code}\n"
            f"Request: {json_body}\n"
            f"Response: {payload}\n"
        )

    return r.json()

def _delete(url: str, *, headers: Dict[str,str], timeout: float = DEFAULT_TIMEOUT) -> None:
    r = requests.delete(url, headers=headers, timeout=timeout)
    # ERPNext may return 200/202 even if already deleted; accept 404 too
    if r.status_code not in (200, 202, 204, 404):
        r.raise_for_status()

def _get(url: str, *, headers: Optional[Dict[str,str]] = None, timeout: float = DEFAULT_TIMEOUT) -> Dict[str,Any]:
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()

def unique_suffix(n: int = 6) -> str:
    import random, string
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))

def create_purchase_invoice_in_erpnext(*, supplier: str, company: str, item_code: str, qty: float, rate: float) -> str:
    """
    Creates a Purchase Invoice in ERPNext via REST API.
    Requires:
      ERP_BASE_URL, ERP_API_KEY, ERP_API_SECRET
    Also requires that `supplier`, `company`, and `item_code` already exist in ERPNext.
    """
    url = f"{erp_base_url()}/api/resource/Purchase%20Invoice"
    body = {
        "supplier": supplier,
        "company": company,
        "posting_date": time.strftime("%Y-%m-%d"),
        "currency": "USD",
        "items": [
            {"item_code": item_code, "qty": qty, "rate": rate}
        ],
        # Unique title field to help debug in ERP UI (optional)
        "remarks": f"live-test-{unique_suffix()}",
    }
    data = _post(url, headers=erp_headers(), json_body=body)
    # Frappe returns {"data": {"name": "ACC-PINV-2026-00001", ...}}
    name = data.get("data", {}).get("name")
    if not name:
        raise RuntimeError(f"Unexpected ERPNext create response: {data}")
    return name

def delete_purchase_invoice_in_erpnext(invoice_name: str) -> None:
    url = f"{erp_base_url()}/api/resource/Purchase%20Invoice/{invoice_name}"
    _delete(url, headers=erp_headers())

def run_backend_sync() -> Dict[str,Any]:
    """
    Calls your backend /sync/run endpoint so the backend pulls from ERPNext and stores to its DB.
    Requires BACKEND_BASE_URL.
    """
    url = f"{backend_base_url()}/sync/run"
    return _post(url, headers={"Content-Type":"application/json"}, json_body={})

def wait_until_invoice_visible(invoice_id: str, *, include_items: bool = True, timeout_s: float = 40, poll_s: float = 2) -> Dict[str,Any]:
    """
    Polls /invoices until the ERP invoice_id appears.
    """
    end = time.time() + timeout_s
    while time.time() < end:
        data = _get(f"{backend_base_url()}/invoices?limit=200&include_items={'true' if include_items else 'false'}")
        rows = data.get("data", [])
        hit = next((x for x in rows if x.get("invoice_id") == invoice_id), None)
        if hit:
            return hit
        time.sleep(poll_s)
    raise AssertionError(f"Invoice {invoice_id} not visible in backend within {timeout_s}s")

def get_dashboard_summary(*, nocache: bool = False):
    url = f"{BACKEND_BASE_URL}/dashboard/summary"
    if nocache:
        url += f"?_ts={int(time.time() * 1000)}"
    return _get(url, headers={"Cache-Control": "no-cache"}, timeout=DEFAULT_TIMEOUT)


def get_risk_anomalies(min_rate: float = 0.6) -> list:
    return _get(f"{backend_base_url()}/risk/anomalies?min_rate={min_rate}&limit=200").get("data", [])

def get_risk_vendors(min_rate: float = 0.0) -> Dict[str,Any]:
    return _get(f"{backend_base_url()}/risk/vendors?min_rate={min_rate}&limit=500").get("data", {})

def recalculate_risk(limit: int = 500) -> Dict[str,Any]:
    return _post(f"{backend_base_url()}/risk/recalculate?limit={limit}", headers={"Content-Type":"application/json"}, json_body={}).get("data", {})


def wait_until_total_increases(
    before_total: int,
    *,
    timeout_seconds: int = 20,
    poll_interval: float = 2.0,
):
    """
    Poll dashboard summary until total_invoices >= before_total + 1
    or timeout expires.
    """
    deadline = time.time() + timeout_seconds

    last_seen = None
    while time.time() < deadline:
        summary = get_dashboard_summary(nocache=True)
        total = int(summary.get("total_invoices", 0))
        last_seen = total

        if total >= before_total + 1:
            return summary

        time.sleep(poll_interval)

    raise AssertionError(
        f"Dashboard total_invoices did not increase within {timeout_seconds}s. "
        f"Expected >= {before_total + 1}, last_seen={last_seen}"
    )
