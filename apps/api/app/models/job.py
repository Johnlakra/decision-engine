"""jobs: Postgres queue claimed with FOR UPDATE SKIP LOCKED (FR-06)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import JobKind, JobStatus


class Job(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(JobKind.check_sql("kind"), name="kind"),
        CheckConstraint(JobStatus.check_sql("status"), name="status"),
        Index(
            "ix_jobs_queued_run_at",
            "run_at",
            postgresql_where=text("status = 'queued'"),
        ),
        Index("ix_jobs_tenant_item", "tenant_id", "item_id"),
    )

    kind: Mapped[str] = mapped_column(Text, nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
