"""feedback: the Laya training set (FR-62)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import FeedbackKind, LabelSource


class Feedback(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint(FeedbackKind.check_sql("kind"), name="kind"),
        CheckConstraint(LabelSource.check_sql("label_source"), name="label_source"),
        Index("ix_feedback_tenant_training", "tenant_id", "used_for_training"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=False
    )
    niche: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    state_text: Mapped[str] = mapped_column(Text, nullable=False)
    questions: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB)
    gold: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    label_source: Mapped[str] = mapped_column(Text, nullable=False, server_default="human")
    used_for_training: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
