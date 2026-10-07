"""api_keys: ``de_<prefix>_<secret>``; only sha256(secret + pepper) is stored (FR-07)."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin


class ApiKey(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_id", "tenant_id"),)

    prefix: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hash: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
