from pydantic import BaseModel
from typing import List, Optional, Any


class InvoiceItemOut(BaseModel):
    item_code: Optional[str] = None
    item_name: Optional[str] = None
    qty: Optional[float] = None
    rate: Optional[float] = None
    amount: Optional[float] = None


class RiskAnalysisOut(BaseModel):
    """Risk analysis data embedded in invoice response."""
    rate: float
    risk_level: str
    reasons: List[Any] = []  # list of dicts with type, severity, message


class InvoiceOut(BaseModel):
    invoice_id: str
    supplier: Optional[str] = None
    posting_date: Optional[str] = None
    grand_total: Optional[float] = None
    erp_modified: Optional[str] = None

    items: List[InvoiceItemOut] = []
    risk: Optional[RiskAnalysisOut] = None
