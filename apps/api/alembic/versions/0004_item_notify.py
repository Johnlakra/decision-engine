"""items.notified_at / digested_at: Telegram ping and digest bookkeeping (FR-43)."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("items", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("items", sa.Column("digested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "digested_at")
    op.drop_column("items", "notified_at")
