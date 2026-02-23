"""
arq job for sending payment failure notification emails.

Pattern matches auth/email.py: logs for dev/test visibility, wraps SMTP send
in try/except so the job never fails on SMTP misconfiguration.
"""

import logging

from wxcode_adm.config import settings

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
    subject = f"[WXCODE] Payment failed for {tenant_name}"
    body = (
        f"Payment has failed for your workspace '{tenant_name}'.\n\n"
        "Your workspace access to the wxcode engine has been restricted.\n"
        "Please update your payment method in the billing settings to restore access.\n\n"
        "You can still access wxcode-adm to manage your account and billing.\n\n"
        "— WXCODE Team"
    )

    # DEV: Log for dev/test access without SMTP configured
    logger.info(f"[DEV] Payment failed email for {email} (tenant: {tenant_name})")

    try:
        from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType  # noqa: PLC0415

        conf = ConnectionConfig(
            MAIL_USERNAME=settings.SMTP_USER,
            MAIL_PASSWORD=settings.SMTP_PASSWORD,
            MAIL_FROM=settings.SMTP_FROM_EMAIL,
            MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
            MAIL_PORT=settings.SMTP_PORT,
            MAIL_SERVER=settings.SMTP_HOST,
            MAIL_STARTTLS=settings.SMTP_TLS,
            MAIL_SSL_TLS=settings.SMTP_SSL,
            USE_CREDENTIALS=bool(settings.SMTP_USER),
        )
        message = MessageSchema(
            subject=subject,
            recipients=[email],
            body=body,
            subtype=MessageType.plain,
        )
        fm = FastMail(conf)
        await fm.send_message(message)
        logger.info(f"Payment failure email sent to {email}")
    except Exception:
        logger.warning(
            f"Failed to send payment failure email to {email} — SMTP may not be configured",
            exc_info=True,
        )
