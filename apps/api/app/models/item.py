"""items: one DecisionItem and its pipeline state (FR-02, FR-06)."""

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import ItemStatus, Risk, Sensitivity

EMBEDDING_DIM = 768


class Item(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "source_ref"),
        CheckConstraint(ItemStatus.check_sql("status"), name="status"),
        CheckConstraint(Sensitivity.check_sql("sensitivity"), name="sensitivity"),
        CheckConstraint(f"risk IS NULL OR {Risk.check_sql('risk')}", name="risk"),
        Index(
            "ix_items_queue",
            "tenant_id",
            "status",
            text("urgency DESC"),
            "deadline_at",
        ),
        Index("ix_items_tenant_created", "tenant_id", "created_at"),
        Index(
            "ix_items_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    language: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    niche: Mapped[str | None] = mapped_column(Text)
    triage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decision: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    risk: Mapped[str | None] = mapped_column(Text)
    urgency: Mapped[int | None] = mapped_column(SmallInteger)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # FR-43 ping
    digested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # FR-43 digest
    related_to: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    hints: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # ADR 0004; never public
    callback_url: Mapped[str | None] = mapped_column(Text)  # stored only in Phase 1; never public
    laya_mode: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
