from __future__ import annotations

from typing import Any

from core.config import Settings
from notify.email_acs import send_email_via_acs
from notify.email_smtp import send_email_via_smtp


def send_email(settings: Settings, subject: str, html_content: str, logger: Any) -> str:
    if settings.dry_run:
        logger.info("dry_run_skip_send_email")
        return "dry_run"

    if settings.has_acs:
        try:
            send_email_via_acs(
                connection_string=settings.acs_connection_string,
                sender=settings.acs_email_sender,
                recipients=settings.email_to,
                subject=subject,
                html_content=html_content,
                logger=logger,
            )
            return "acs"
        except Exception as exc:
            logger.exception("acs_send_failed_try_smtp", extra={"error": str(exc)})

    if settings.has_smtp:
        send_email_via_smtp(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            sender=settings.smtp_from,
            recipients=settings.email_to,
            subject=subject,
            html_content=html_content,
            use_tls=settings.smtp_use_tls,
            use_ssl=settings.smtp_use_ssl,
            logger=logger,
        )
        return "smtp"

    raise RuntimeError("No available email backend (ACS/SMTP)")
