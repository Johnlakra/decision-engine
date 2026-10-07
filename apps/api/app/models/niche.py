"""niches: DB rows override YAML niches of the same name."""

from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.models.enums import NicheSource


class Niche(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "niches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name"),
        CheckConstraint(NicheSource.check_sql("source"), name="source"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="db")
