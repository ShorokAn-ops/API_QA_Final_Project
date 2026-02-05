import httpx
from core.config import settings


class ERPClient:
    def __init__(self) -> None:
        self.base = settings.ERPNEXT_BASE_URL.rstrip("/")
        self.headers = {
            "Authorization": f"token {settings.ERPNEXT_API_KEY}:{settings.ERPNEXT_API_SECRET}",
            "Accept": "application/json",
        }

    async def list_purchase_invoices(self, limit: int = 500) -> list[dict]:
        """
        Minimal fields + modified for delta decisions.
        Works with ERPNext REST: /api/resource/Purchase Invoice
        """
        url = f"{self.base}/api/resource/Purchase%20Invoice"
        params = {
            "fields": '["name","supplier","posting_date","grand_total","modified"]',
            "limit_page_length": str(limit),
            "order_by": "modified desc",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=self.headers, params=params)
            r.raise_for_status()
            return (r.json().get("data") or [])

    async def get_purchase_invoice(self, name: str) -> dict:
        url = f"{self.base}/api/resource/Purchase%20Invoice/{name}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url, headers=self.headers)
            r.raise_for_status()
            return (r.json().get("data") or {})

    async def delete_purchase_invoice(self, name: str) -> None:
        """
        Delete a Purchase Invoice from ERPNext.
        Used for test cleanup.
        """
        url = f"{self.base}/api/resource/Purchase%20Invoice/{name}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.delete(url, headers=self.headers)
            r.raise_for_status()
