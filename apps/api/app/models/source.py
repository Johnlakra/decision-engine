"""sources: where items come from. Tokens are Fernet-encrypted (NFR-07)."""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import Sensitivity


class Source(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug"),
        CheckConstraint(Sensitivity.check_sql("sensitivity"), name="sensitivity"),
    )

    type: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    secret_enc: Mapped[str | None] = mapped_column(Text)
    oauth_enc: Mapped[str | None] = mapped_column(Text)
    niche_hint: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    cursor: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
