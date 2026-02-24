"""
arq job for sending payment failure notification emails.

Pattern matches auth/email.py: logs for dev/test visibility, wraps SMTP send
in try/except so the job never fails on SMTP misconfiguration.

Phase 5: Sends branded HTML+plain-text multipart email using the shared
FastMail singleton and templates/email/payment_failed.html template.
"""

import logging

logger = logging.getLogger(__name__)


async def send_payment_failed_email(ctx: dict, email: str, tenant_name: str) -> None:
    """
    Send payment failure notification email to a tenant owner or billing admin.

    Follows the same pattern as auth/email.py send_verification_email:
    - Logs at INFO for dev/test access without SMTP.
    - Wraps actual SMTP send in try/except — job does NOT fail on SMTP error.

    Args:
        ctx: arq job context (provided automatically by the worker).
        email: Recipient email address (owner or billing_access member).
        tenant_name: Display name of the workspace with the failed payment.
    """
    # DEV: Log for dev/test access without SMTP configured
    logger.info(f"[DEV] Payment failed email for {email} (tenant: {tenant_name})")

    try:
        from fastapi_mail import MessageSchema, MessageType  # noqa: PLC0415

        from wxcode_adm.common.mail import fast_mail  # noqa: PLC0415
        from wxcode_adm.config import settings  # noqa: PLC0415

        message = MessageSchema(
            subject=f"[WXCODE] Payment failed for {tenant_name}",
            recipients=[email],
            template_body={
                "tenant_name": tenant_name,
                "email": email,
                "billing_url": f"{settings.FRONTEND_URL}/billing",
            },
            subtype=MessageType.html,
        )
        await fast_mail.send_message(
            message,
            html_template="payment_failed.html",
            plain_template="payment_failed.txt",
        )
        logger.info(f"Payment failure email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send payment failure email to {email} \u2014 SMTP may not be configured",
            exc_info=True,
        )
