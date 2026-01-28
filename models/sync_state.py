from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from models.base import Base


class SyncState(Base):
    __tablename__ = "sync_state"

    id = Column(Integer, primary_key=True)
    key = Column(String(64), unique=True, nullable=False)  # e.g. "purchase_invoice_last_modified"
    value = Column(String(255), nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
