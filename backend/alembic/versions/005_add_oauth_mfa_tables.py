"""add oauth and mfa tables

Revision ID: 005
Revises: 004
Create Date: 2026-02-24 18:30:00.000000

Phase 6 — OAuth and MFA schema changes:
- ALTER users: add mfa_enabled, mfa_secret; make password_hash nullable
- ALTER tenants: add mfa_enforced
- CREATE oauth_accounts: provider identity linking table
- CREATE mfa_backup_codes: hashed one-time recovery codes
- CREATE trusted_devices: long-lived device trust tokens
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add OAuth and MFA schema changes for Phase 6."""

    # ---------------------------------------------------------------------------
    # 1. ALTER users table — add MFA columns and make password_hash nullable
    # ---------------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "mfa_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "mfa_secret",
            sa.String(64),
            nullable=True,
        ),
    )
    # Make password_hash nullable (OAuth-only accounts have no password)
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=True,
    )

    # ---------------------------------------------------------------------------
    # 2. ALTER tenants table — add mfa_enforced column
    # ---------------------------------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "mfa_enforced",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # ---------------------------------------------------------------------------
    # 3. CREATE TABLE oauth_accounts
    # ---------------------------------------------------------------------------
    op.create_table(
        "oauth_accounts",
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
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_oauth_accounts_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
        sa.UniqueConstraint(
            "provider",
            "provider_user_id",
            name="uq_oauth_accounts_provider_provider_user_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name="uq_oauth_accounts_user_provider",
        ),
    )
    op.create_index(
        op.f("ix_oauth_accounts_user_id"),
        "oauth_accounts",
        ["user_id"],
    )

    # ---------------------------------------------------------------------------
    # 4. CREATE TABLE mfa_backup_codes
    # ---------------------------------------------------------------------------
    op.create_table(
        "mfa_backup_codes",
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
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_mfa_backup_codes_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_backup_codes")),
    )
    op.create_index(
        op.f("ix_mfa_backup_codes_user_id"),
        "mfa_backup_codes",
        ["user_id"],
    )

    # ---------------------------------------------------------------------------
    # 5. CREATE TABLE trusted_devices
    # ---------------------------------------------------------------------------
    op.create_table(
        "trusted_devices",
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
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name=op.f("fk_trusted_devices_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trusted_devices")),
        sa.UniqueConstraint(
            "token_hash",
            name=op.f("uq_trusted_devices_token_hash"),
        ),
    )
    op.create_index(
        op.f("ix_trusted_devices_user_id"),
        "trusted_devices",
        ["user_id"],
    )


def downgrade() -> None:
    """Reverse all Phase 6 schema changes."""

    # 5. DROP trusted_devices
    op.drop_index(op.f("ix_trusted_devices_user_id"), table_name="trusted_devices")
    op.drop_table("trusted_devices")

    # 4. DROP mfa_backup_codes
    op.drop_index(op.f("ix_mfa_backup_codes_user_id"), table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")

    # 3. DROP oauth_accounts
    op.drop_index(op.f("ix_oauth_accounts_user_id"), table_name="oauth_accounts")
    op.drop_table("oauth_accounts")

    # 2. ALTER tenants — remove mfa_enforced
    op.drop_column("tenants", "mfa_enforced")

    # 1. ALTER users — restore password_hash NOT NULL, drop mfa columns
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(255),
        nullable=False,
    )
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
