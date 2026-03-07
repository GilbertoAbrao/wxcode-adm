"""
SQLAlchemy models for wxcode-adm billing domain.

Plan is a platform-level model managed by super-admin — it defines the billing
tiers available to tenants. TenantSubscription links a tenant to a plan with
Stripe subscription state. WebhookEvent provides idempotent event processing.

IMPORTANT: All 3 models inherit Base+TimestampMixin (NOT TenantModel). These
are platform-level records, not tenant-scoped data. The TenantModel base class
is for domain data that lives inside a tenant (scoped by tenant_id guard).

Design decisions (from 04-CONTEXT.md and 04-RESEARCH.md):
- native_enum=False on SubscriptionStatus Enum — avoids PostgreSQL CREATE TYPE
  and Alembic migration pitfalls (same pattern as MemberRole in tenants).
- overage_rate_cents_per_token stored as integer hundredths of a cent
  (e.g., 4 = $0.00004/token) for precision without floating point.
- member_cap=-1 means unlimited members (free tier uses 1 or small cap).
- Plan soft-deleted via is_active=False — hard delete blocked if subscriptions
  reference the plan via foreign key.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from wxcode_adm.db.base import Base, TimestampMixin


class SubscriptionStatus(enum.Enum):
    """
    Billing subscription states.

    FREE: tenant on free tier (no Stripe subscription).
    ACTIVE: paid subscription current.
    PAST_DUE: payment failed, grace period.
    CANCELED: subscription canceled.
    """

    FREE = "free"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class Plan(TimestampMixin, Base):
    """
    A billing plan/tier available to tenants.

    Platform-level — managed by super-admin only.
    Stripe IDs are populated after creation is synced to Stripe.
    stripe_overage_price_id references a metered Price linked to the Billing Meter.
    """

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    stripe_product_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    stripe_price_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    stripe_meter_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    stripe_overage_price_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    monthly_fee_cents: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    token_quota: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    overage_rate_cents_per_token: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    member_cap: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    max_projects: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    max_output_projects: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
    )
    max_storage_gb: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    def __repr__(self) -> str:
        return f"Plan(id={self.id!r}, slug={self.slug!r}, active={self.is_active!r})"


class TenantSubscription(TimestampMixin, Base):
    """
    Links a tenant to a billing plan with Stripe subscription state.

    One record per tenant (unique=True on tenant_id). Tracks the active
    Stripe customer, subscription, billing period, and token usage.
    The plan relationship is loaded eagerly (lazy="joined") since subscription
    checks almost always need the plan details.
    """

    __tablename__ = "tenant_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plans.id"),
        nullable=False,
    )
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        sqlalchemy.Enum(SubscriptionStatus, native_enum=False, length=20),
        nullable=False,
    )
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tokens_used_this_period: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    plan: Mapped["Plan"] = relationship(lazy="joined")
    tenant: Mapped["Tenant"] = relationship(lazy="joined")  # type: ignore[name-defined]  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"TenantSubscription(tenant_id={self.tenant_id!r}, "
            f"plan_id={self.plan_id!r}, status={self.status!r})"
        )


class WebhookEvent(TimestampMixin, Base):
    """
    Idempotency log for processed Stripe webhook events.

    stripe_event_id is unique — duplicate events (Stripe may deliver events
    more than once) are detected here before processing. processed_at is set
    after successful handling.
    """

    __tablename__ = "webhook_events"

    stripe_event_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"WebhookEvent(stripe_event_id={self.stripe_event_id!r}, "
            f"event_type={self.event_type!r})"
        )
