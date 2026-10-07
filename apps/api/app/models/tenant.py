"""tenants: one row at MVP."""

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Asia/Kolkata")
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default="free")
