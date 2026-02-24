"""
Shared FastMail singleton for wxcode-adm.

Constructed once at module load with TEMPLATE_FOLDER pointing to the
templates/email directory. All email sender functions import this singleton
instead of constructing per-call ConnectionConfig + FastMail instances.
"""

from pathlib import Path

from fastapi_mail import ConnectionConfig, FastMail

from wxcode_adm.config import settings

_mail_conf = ConnectionConfig(
    MAIL_USERNAME=settings.SMTP_USER,
    MAIL_PASSWORD=settings.SMTP_PASSWORD,
    MAIL_FROM=settings.SMTP_FROM_EMAIL,
    MAIL_FROM_NAME=settings.SMTP_FROM_NAME,
    MAIL_PORT=settings.SMTP_PORT,
    MAIL_SERVER=settings.SMTP_HOST,
    MAIL_STARTTLS=settings.SMTP_TLS,
    MAIL_SSL_TLS=settings.SMTP_SSL,
    USE_CREDENTIALS=bool(settings.SMTP_USER),
    TEMPLATE_FOLDER=Path(__file__).parent.parent / "templates" / "email",
)

fast_mail = FastMail(_mail_conf)
