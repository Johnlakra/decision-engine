"""decisions: append-only record of every verdict."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import DecidedBy, Verdict


class Decision(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "decisions"
    __table_args__ = (
        CheckConstraint(Verdict.check_sql("verdict"), name="verdict"),
        CheckConstraint(DecidedBy.check_sql("decided_by"), name="decided_by"),
        Index("ix_decisions_tenant_item", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    option: Mapped[str | None] = mapped_column(Text)
    edits: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decided_by: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column()
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
