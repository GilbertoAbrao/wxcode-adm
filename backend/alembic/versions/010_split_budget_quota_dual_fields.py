"""Split budget/quota into dual time-window fields

Revision ID: 010
Revises: 009
Create Date: 2026-03-08 00:00:00.000000

Phase 23 — Dual time-window budget/quota fields:
- ALTER tenants: drop claude_monthly_token_budget,
  add claude_5h_token_budget + claude_weekly_token_budget
- ALTER plans: drop token_quota,
  add token_quota_5h + token_quota_weekly

Data migration copies existing values to both new columns so no data
is lost during upgrade. Downgrade reverses the process using 5h values.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Split single budget/quota columns into dual time-window columns."""

    # -----------------------------------------------------------------------
    # Tenants: replace claude_monthly_token_budget with two window columns
    # -----------------------------------------------------------------------

    # 1. Add claude_5h_token_budget (nullable, no server default — data migration fills it)
    op.add_column(
        "tenants",
        sa.Column(
            "claude_5h_token_budget",
            sa.Integer(),
            nullable=True,
        ),
    )

    # 2. Add claude_weekly_token_budget (nullable, no server default — data migration fills it)
    op.add_column(
        "tenants",
        sa.Column(
            "claude_weekly_token_budget",
            sa.Integer(),
            nullable=True,
        ),
    )

    # 3. Copy existing values to both new columns
    op.execute(
        text(
            "UPDATE tenants SET claude_5h_token_budget = claude_monthly_token_budget, "
            "claude_weekly_token_budget = claude_monthly_token_budget"
        )
    )

    # 4. Drop the old column
    op.drop_column("tenants", "claude_monthly_token_budget")

    # -----------------------------------------------------------------------
    # Plans: replace token_quota with two window columns
    # -----------------------------------------------------------------------

    # 5. Add token_quota_5h (non-nullable, server_default=0 for existing rows)
    op.add_column(
        "plans",
        sa.Column(
            "token_quota_5h",
            sa.Integer(),
            nullable=False,
            server_default=text("0"),
        ),
    )

    # 6. Add token_quota_weekly (non-nullable, server_default=0 for existing rows)
    op.add_column(
        "plans",
        sa.Column(
            "token_quota_weekly",
            sa.Integer(),
            nullable=False,
            server_default=text("0"),
        ),
    )

    # 7. Copy existing token_quota values to both new columns
    op.execute(
        text(
            "UPDATE plans SET token_quota_5h = token_quota, token_quota_weekly = token_quota"
        )
    )

    # 8. Drop the old column
    op.drop_column("plans", "token_quota")


def downgrade() -> None:
    """Restore single budget/quota columns from dual time-window columns."""

    # -----------------------------------------------------------------------
    # Plans: restore token_quota from token_quota_5h
    # -----------------------------------------------------------------------

    # 1. Add token_quota back (non-nullable, server_default=0 for safety)
    op.add_column(
        "plans",
        sa.Column(
            "token_quota",
            sa.Integer(),
            nullable=False,
            server_default=text("0"),
        ),
    )

    # 2. Copy token_quota_5h back to token_quota
    op.execute(text("UPDATE plans SET token_quota = token_quota_5h"))

    # 3. Drop the two new plan columns
    op.drop_column("plans", "token_quota_weekly")
    op.drop_column("plans", "token_quota_5h")

    # -----------------------------------------------------------------------
    # Tenants: restore claude_monthly_token_budget from claude_5h_token_budget
    # -----------------------------------------------------------------------

    # 4. Add claude_monthly_token_budget back (nullable)
    op.add_column(
        "tenants",
        sa.Column(
            "claude_monthly_token_budget",
            sa.Integer(),
            nullable=True,
        ),
    )

    # 5. Copy claude_5h_token_budget to claude_monthly_token_budget
    op.execute(
        text(
            "UPDATE tenants SET claude_monthly_token_budget = claude_5h_token_budget"
        )
    )

    # 6. Drop the two new tenant columns
    op.drop_column("tenants", "claude_weekly_token_budget")
    op.drop_column("tenants", "claude_5h_token_budget")
