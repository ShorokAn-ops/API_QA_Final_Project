from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.base import Base


class RiskAnalysis(Base):
    __tablename__ = "risk_analysis"

    id = Column(Integer, primary_key=True)
    invoice_id_fk = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), unique=True, nullable=False)

    rate = Column(Float, nullable=False, default=0.0)
    risk_level = Column(String(32), nullable=False, default="LOW")
    reasons = Column(JSON, nullable=False, default=list)

    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice = relationship("Invoice", back_populates="risk")
