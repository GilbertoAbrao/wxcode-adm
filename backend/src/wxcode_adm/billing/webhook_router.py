"""
Stripe webhook ingestion router for wxcode-adm.

This is a SEPARATE file from router.py because it has fundamentally different
auth requirements: no JWT auth, uses Stripe-Signature header for verification.

Fast path design:
- Verify Stripe signature (reject invalid payloads immediately)
- Enqueue event to arq for async processing (return 200 quickly)
- Stripe retries on non-2xx, so responding fast is critical

Deduplication:
- arq _job_id = Stripe event ID (atomic Redis deduplication while job is queued/running)
- WebhookEvent table in DB provides permanent idempotency (outlasts arq result TTL)
"""

from __future__ import annotations

import logging
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from wxcode_adm.config import settings
from wxcode_adm.tasks.worker import get_arq_pool

logger = logging.getLogger(__name__)

webhook_router = APIRouter(tags=["Webhooks"])


async def get_raw_body(request: Request) -> bytes:
    """
    Read raw request body as bytes.

    CRITICAL: Must NOT parse as JSON — Stripe signature verification
    requires the exact wire bytes. Any JSON parsing produces different
    byte representation and breaks verification.
    """
    return await request.body()


@webhook_router.post("/webhooks/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str, Header(alias="stripe-signature")],
    body: bytes = Depends(get_raw_body),
) -> dict:
    """
    Stripe webhook ingestion endpoint.

    Fast path: verify signature, enqueue to arq, return 200.
    Processing happens asynchronously in the arq worker.
    Stripe retries on non-2xx, so returning 200 quickly is critical.

    Auth: Stripe-Signature header (NOT JWT). This endpoint must NOT
    use require_verified or any JWT auth dependency.
    """
    try:
        event = stripe.Webhook.construct_event(
            payload=body,
            sig_header=stripe_signature,
            secret=settings.STRIPE_WEBHOOK_SECRET.get_secret_value(),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    # Enqueue with _job_id = Stripe event ID for arq-level deduplication.
    # arq atomic Redis transaction guarantees no duplicate enqueue while
    # the job is still queued or running.
    pool = await get_arq_pool()
    try:
        await pool.enqueue_job(
            "process_stripe_event",
            event["id"],
            event["type"],
            event["data"]["object"],
            _job_id=event["id"],
        )
    finally:
        await pool.aclose()

    logger.info(f"Webhook received and enqueued: {event['type']} ({event['id']})")
    return {"received": True}
