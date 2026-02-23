"""add tenants, tenant_memberships, invitations, and ownership_transfers tables

Revision ID: 002
Revises: 001
Create Date: 2026-02-23 15:52:06.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the tenants, tenant_memberships, invitations, and ownership_transfers tables."""

    # -- tenants -------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=True)

    # -- tenant_memberships --------------------------------------------------
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("billing_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_tenant_memberships_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_memberships_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_tenant_memberships_invited_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_memberships")),
        sa.UniqueConstraint("user_id", "tenant_id", name=op.f("uq_tenant_memberships_user_tenant")),
    )
    op.create_index(op.f("ix_tenant_memberships_user_id"), "tenant_memberships", ["user_id"], unique=False)
    op.create_index(op.f("ix_tenant_memberships_tenant_id"), "tenant_memberships", ["tenant_id"], unique=False)

    # -- invitations ---------------------------------------------------------
    op.create_table(
        "invitations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("billing_access", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_invitations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_id"],
            ["users.id"],
            name=op.f("fk_invitations_invited_by_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_invitations")),
        sa.UniqueConstraint("email", "tenant_id", name=op.f("uq_invitations_email_tenant")),
    )
    op.create_index(op.f("ix_invitations_email"), "invitations", ["email"], unique=False)
    op.create_index(op.f("ix_invitations_tenant_id"), "invitations", ["tenant_id"], unique=False)

    # -- ownership_transfers -------------------------------------------------
    op.create_table(
        "ownership_transfers",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("from_user_id", sa.UUID(), nullable=False),
        sa.Column("to_user_id", sa.UUID(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ownership_transfers_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_user_id"],
            ["users.id"],
            name=op.f("fk_ownership_transfers_from_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_user_id"],
            ["users.id"],
            name=op.f("fk_ownership_transfers_to_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ownership_transfers")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_ownership_transfers_tenant_id")),
    )
    op.create_index(op.f("ix_ownership_transfers_tenant_id"), "ownership_transfers", ["tenant_id"], unique=True)


def downgrade() -> None:
    """Drop the ownership_transfers, invitations, tenant_memberships, and tenants tables."""
    op.drop_index(op.f("ix_ownership_transfers_tenant_id"), table_name="ownership_transfers")
    op.drop_table("ownership_transfers")

    op.drop_index(op.f("ix_invitations_tenant_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_email"), table_name="invitations")
    op.drop_table("invitations")

    op.drop_index(op.f("ix_tenant_memberships_tenant_id"), table_name="tenant_memberships")
    op.drop_index(op.f("ix_tenant_memberships_user_id"), table_name="tenant_memberships")
    op.drop_table("tenant_memberships")

    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")
