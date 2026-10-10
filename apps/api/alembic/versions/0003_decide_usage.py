"""decide_usage: per-tenant daily counter for POST /v1/decide (code review M3; FR-35, NFR-05)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-10 09:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decide_usage",
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("calls", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("calls >= 0", name=op.f("ck_decide_usage_calls_nonneg")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_decide_usage_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "day", name=op.f("pk_decide_usage")),
    )


def downgrade() -> None:
    op.drop_table("decide_usage")
