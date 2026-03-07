"""Add wxcode plan limit fields to plans table

Revision ID: 009
Revises: 008
Create Date: 2026-03-07 00:00:00.000000

Phase 21 — Plan limits extension for wxcode engine integration:
- ALTER plans: add max_projects, max_output_projects, max_storage_gb

These integer columns define per-tenant operational limits that the wxcode
engine enforces. Phase 23 (Admin UI - Claude Management) exposes them in
the admin plan form so super-admins can configure limits per plan tier.

Non-nullable columns use server_default so existing rows receive correct
defaults without a data migration (same pattern as migration 008).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 21 wxcode plan limit columns to plans table."""

    # -----------------------------------------------------------------------
    # 1. max_projects — maximum wxcode projects per tenant, default 5
    # -----------------------------------------------------------------------
    op.add_column(
        "plans",
        sa.Column(
            "max_projects",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )

    # -----------------------------------------------------------------------
    # 2. max_output_projects — maximum output projects per tenant, default 20
    # -----------------------------------------------------------------------
    op.add_column(
        "plans",
        sa.Column(
            "max_output_projects",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("20"),
        ),
    )

    # -----------------------------------------------------------------------
    # 3. max_storage_gb — maximum storage in GB per tenant, default 10
    # -----------------------------------------------------------------------
    op.add_column(
        "plans",
        sa.Column(
            "max_storage_gb",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    )


def downgrade() -> None:
    """Drop Phase 21 plan limit columns from plans table in reverse order."""

    op.drop_column("plans", "max_storage_gb")
    op.drop_column("plans", "max_output_projects")
    op.drop_column("plans", "max_projects")
