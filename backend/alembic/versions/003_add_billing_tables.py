"""add plans, tenant_subscriptions, and webhook_events tables

Revision ID: 003
Revises: 002
Create Date: 2026-02-23 19:54:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the plans, tenant_subscriptions, and webhook_events tables."""

    # -- plans ---------------------------------------------------------------
    op.create_table(
        "plans",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("stripe_product_id", sa.String(255), nullable=True),
        sa.Column("stripe_price_id", sa.String(255), nullable=True),
        sa.Column("stripe_meter_id", sa.String(255), nullable=True),
        sa.Column("stripe_overage_price_id", sa.String(255), nullable=True),
        sa.Column("monthly_fee_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_quota", sa.Integer(), nullable=False),
        sa.Column("overage_rate_cents_per_token", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("member_cap", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plans")),
        sa.UniqueConstraint("slug", name=op.f("uq_plans_slug")),
    )
    op.create_index(op.f("ix_plans_slug"), "plans", ["slug"], unique=True)

    # -- tenant_subscriptions ------------------------------------------------
    op.create_table(
        "tenant_subscriptions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tokens_used_this_period", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_subscriptions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name=op.f("fk_tenant_subscriptions_plan_id_plans"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_subscriptions")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_tenant_subscriptions_tenant_id")),
    )
    op.create_index(op.f("ix_tenant_subscriptions_tenant_id"), "tenant_subscriptions", ["tenant_id"], unique=True)

    # -- webhook_events ------------------------------------------------------
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("stripe_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_events")),
        sa.UniqueConstraint("stripe_event_id", name=op.f("uq_webhook_events_stripe_event_id")),
    )
    op.create_index(op.f("ix_webhook_events_stripe_event_id"), "webhook_events", ["stripe_event_id"], unique=True)


def downgrade() -> None:
    """Drop the webhook_events, tenant_subscriptions, and plans tables."""
    op.drop_index(op.f("ix_webhook_events_stripe_event_id"), table_name="webhook_events")
    op.drop_table("webhook_events")

    op.drop_index(op.f("ix_tenant_subscriptions_tenant_id"), table_name="tenant_subscriptions")
    op.drop_table("tenant_subscriptions")

    op.drop_index(op.f("ix_plans_slug"), table_name="plans")
    op.drop_table("plans")
