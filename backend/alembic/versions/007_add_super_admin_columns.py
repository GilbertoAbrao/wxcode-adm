"""add super admin columns

Revision ID: 007
Revises: 006
Create Date: 2026-02-26 00:00:00.000000

Phase 8 — Super-Admin schema changes:
- ALTER tenants: add is_suspended, is_deleted Boolean columns
- ALTER tenant_memberships: add is_blocked Boolean column
- ALTER users: add password_reset_required Boolean column

All columns use server_default=false so existing rows get False immediately
without requiring a data migration (per research anti-pattern: "forgetting
is_deleted default False").
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 8 super-admin Boolean flag columns to existing tables."""

    # ---------------------------------------------------------------------------
    # 1. ALTER tenants — add is_suspended and is_deleted
    # ---------------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "is_suspended",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ---------------------------------------------------------------------------
    # 2. ALTER tenant_memberships — add is_blocked
    # ---------------------------------------------------------------------------
    op.add_column(
        "tenant_memberships",
        sa.Column(
            "is_blocked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ---------------------------------------------------------------------------
    # 3. ALTER users — add password_reset_required
    # ---------------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "password_reset_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    """Reverse all Phase 8 super-admin column additions."""

    # Reverse in order (opposite of upgrade)
    op.drop_column("users", "password_reset_required")
    op.drop_column("tenant_memberships", "is_blocked")
    op.drop_column("tenants", "is_deleted")
    op.drop_column("tenants", "is_suspended")
