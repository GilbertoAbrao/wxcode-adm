"""Add Claude and wxcode fields to tenants table

Revision ID: 008
Revises: 007
Create Date: 2026-03-07 00:00:00.000000

Phase 20 — Tenant model extension for wxcode engine integration:
- ALTER tenants: add claude_oauth_token, claude_default_model,
  claude_max_concurrent_sessions, claude_monthly_token_budget,
  database_name, default_target_stack, neo4j_enabled, status

Non-nullable columns use server_default so existing rows receive correct
defaults without a data migration (same pattern as migration 007).

claude_oauth_token uses String(2048) to accommodate Fernet-encrypted values
which are longer than the original plaintext OAuth token.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 20 Claude and wxcode integration columns to tenants table."""

    # -----------------------------------------------------------------------
    # 1. claude_oauth_token — nullable (null = not configured)
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "claude_oauth_token",
            sa.String(2048),
            nullable=True,
        ),
    )

    # -----------------------------------------------------------------------
    # 2. claude_default_model — default "sonnet"
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "claude_default_model",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'sonnet'"),
        ),
    )

    # -----------------------------------------------------------------------
    # 3. claude_max_concurrent_sessions — default 3
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "claude_max_concurrent_sessions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
    )

    # -----------------------------------------------------------------------
    # 4. claude_monthly_token_budget — nullable (null = unlimited)
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "claude_monthly_token_budget",
            sa.Integer(),
            nullable=True,
        ),
    )

    # -----------------------------------------------------------------------
    # 5. database_name — nullable (null = not provisioned yet)
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "database_name",
            sa.String(100),
            nullable=True,
        ),
    )

    # -----------------------------------------------------------------------
    # 6. default_target_stack — default "fastapi-jinja2"
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "default_target_stack",
            sa.String(50),
            nullable=False,
            server_default=sa.text("'fastapi-jinja2'"),
        ),
    )

    # -----------------------------------------------------------------------
    # 7. neo4j_enabled — default True
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "neo4j_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # -----------------------------------------------------------------------
    # 8. status — plain String (avoids PostgreSQL native enum), default pending_setup
    # -----------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending_setup'"),
        ),
    )


def downgrade() -> None:
    """Drop Phase 20 columns from tenants table in reverse order."""

    op.drop_column("tenants", "status")
    op.drop_column("tenants", "neo4j_enabled")
    op.drop_column("tenants", "default_target_stack")
    op.drop_column("tenants", "database_name")
    op.drop_column("tenants", "claude_monthly_token_budget")
    op.drop_column("tenants", "claude_max_concurrent_sessions")
    op.drop_column("tenants", "claude_default_model")
    op.drop_column("tenants", "claude_oauth_token")
