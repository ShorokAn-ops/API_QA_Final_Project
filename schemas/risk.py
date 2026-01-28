from pydantic import BaseModel
from typing import List, Optional, Any


class RiskOut(BaseModel):
    invoice_id: str
    supplier: Optional[str] = None

    rate: float
    risk_level: str
    reasons: List[Any]  # list[str] or list[dict]
