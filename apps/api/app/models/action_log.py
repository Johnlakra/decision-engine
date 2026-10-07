"""actions_log: idempotent record of every executed action."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import ActionStatus


class ActionLog(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "actions_log"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idem_key"),
        CheckConstraint(ActionStatus.check_sql("status"), name="status"),
        Index("ix_actions_log_tenant_item", "tenant_id", "item_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    idem_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reversible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
