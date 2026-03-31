from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any


def send_email_via_smtp(
    host: str,
    port: int,
    username: str,
    password: str,
    sender: str,
    recipients: list[str],
    subject: str,
    html_content: str,
    use_tls: bool,
    use_ssl: bool,
    logger: Any,
) -> None:
    if not host or not sender:
        raise ValueError("SMTP settings are not complete")
    if not recipients:
        raise ValueError("no email recipients")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    if use_ssl:
        smtp = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)

    try:
        smtp.ehlo()
        if use_tls:
            smtp.starttls()
            smtp.ehlo()
        if username:
            try:
                smtp.login(username, password)
            except smtplib.SMTPAuthenticationError as exc:
                # Common for Microsoft 365 tenants when Authenticated SMTP (basic auth) is disabled.
                raw = (exc.smtp_error or b"")
                raw_text = raw.decode("utf-8", errors="ignore") if isinstance(raw, (bytes, bytearray)) else str(raw)
                if "5.7.139" in raw_text or "basic authentication is disabled" in raw_text.lower():
                    raise RuntimeError(
                        "SMTP authentication failed: Microsoft 365 has disabled basic auth for SMTP. "
                        "Enable 'Authenticated SMTP' for this mailbox (and tenant) or use another email backend. "
                        "If you use MFA, ensure you're using an app password where supported."
                    ) from exc
                raise
        smtp.sendmail(sender, recipients, msg.as_string())
    finally:
        smtp.quit()

    logger.info("email_sent", extra={"backend": "smtp", "recipient_count": len(recipients)})
