from sqlalchemy import Column, Integer, String, Date, Float, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from models.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    invoice_id = Column(String(140), unique=True, index=True, nullable=False)  # ERPNext "name"
    supplier = Column(String(255), index=True, nullable=True)
    posting_date = Column(String(32), nullable=True)  # keep simple string; you can convert to Date later
    grand_total = Column(Float, nullable=True)

    erp_modified = Column(String(32), index=True, nullable=True)
    items_hash = Column(String(64), index=True, nullable=True)

    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    risk = relationship("RiskAnalysis", back_populates="invoice", uselist=False, cascade="all, delete-orphan")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        UniqueConstraint("invoice_id_fk", "item_code", "idx", name="uq_invoice_item"),
    )

    id = Column(Integer, primary_key=True)
    invoice_id_fk = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)

    idx = Column(Integer, nullable=True)  # ERPNext idx
    item_code = Column(String(140), nullable=True)
    item_name = Column(String(255), nullable=True)

    qty = Column(Float, nullable=True)
    rate = Column(Float, nullable=True)   # unit price
    amount = Column(Float, nullable=True)

    invoice = relationship("Invoice", back_populates="items")
