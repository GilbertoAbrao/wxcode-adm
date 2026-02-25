"""add user sessions and profile columns

Revision ID: 006
Revises: 005
Create Date: 2026-02-25 21:06:00.000000

Phase 7 — User Account schema changes:
- CREATE user_sessions: rich session metadata linked 1:1 to refresh_tokens
- ALTER users: add display_name, avatar_url, last_used_tenant_id
- ALTER tenants: add wxcode_url
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add Phase 7 user session tracking and profile column schema changes."""

    # ---------------------------------------------------------------------------
    # 1. CREATE TABLE user_sessions
    # ---------------------------------------------------------------------------
    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("refresh_token_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("access_token_jti", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("browser_name", sa.String(100), nullable=True),
        sa.Column("browser_version", sa.String(50), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["refresh_token_id"],
            ["refresh_tokens.id"],
            ondelete="CASCADE",
            name=op.f("fk_user_sessions_refresh_token_id_refresh_tokens"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_user_sessions_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_sessions")),
        sa.UniqueConstraint(
            "refresh_token_id",
            name=op.f("uq_user_sessions_refresh_token_id"),
        ),
        sa.UniqueConstraint(
            "access_token_jti",
            name=op.f("uq_user_sessions_access_token_jti"),
        ),
    )
    op.create_index(
        op.f("ix_user_sessions_refresh_token_id"),
        "user_sessions",
        ["refresh_token_id"],
    )
    op.create_index(
        op.f("ix_user_sessions_user_id"),
        "user_sessions",
        ["user_id"],
    )

    # ---------------------------------------------------------------------------
    # 2. ALTER users table — add profile columns
    # ---------------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "display_name",
            sa.String(255),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "avatar_url",
            sa.String(512),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_used_tenant_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        op.f("fk_users_last_used_tenant_id_tenants"),
        "users",
        "tenants",
        ["last_used_tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---------------------------------------------------------------------------
    # 3. ALTER tenants table — add wxcode_url column
    # ---------------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "wxcode_url",
            sa.String(2048),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Reverse all Phase 7 schema changes."""

    # 3. DROP wxcode_url from tenants
    op.drop_column("tenants", "wxcode_url")

    # 2. DROP profile columns from users
    op.drop_constraint(
        op.f("fk_users_last_used_tenant_id_tenants"),
        "users",
        type_="foreignkey",
    )
    op.drop_column("users", "last_used_tenant_id")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")

    # 1. DROP user_sessions table
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_refresh_token_id"), table_name="user_sessions")
    op.drop_table("user_sessions")
