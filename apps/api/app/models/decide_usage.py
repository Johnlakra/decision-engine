"""decide_usage: calls to POST /v1/decide per tenant per UTC day (code review M3)."""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DecideUsage(Base):
    __tablename__ = "decide_usage"
    __table_args__ = (CheckConstraint("calls >= 0", name="calls_nonneg"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
