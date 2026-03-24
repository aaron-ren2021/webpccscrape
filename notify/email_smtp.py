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
            smtp.login(username, password)
        smtp.sendmail(sender, recipients, msg.as_string())
    finally:
        smtp.quit()

    logger.info("email_sent", extra={"backend": "smtp", "recipient_count": len(recipients)})
