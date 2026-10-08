"""items.hints, items.callback_url, ix_items_tenant_created (FR-01, FR-06, FR-07; ADR 0004)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 12:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    hints = sa.Column("hints", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    op.add_column("items", hints)
    op.add_column("items", sa.Column("callback_url", sa.Text(), nullable=True))
    op.create_index("ix_items_tenant_created", "items", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_items_tenant_created", table_name="items")
    op.drop_column("items", "callback_url")
    op.drop_column("items", "hints")
