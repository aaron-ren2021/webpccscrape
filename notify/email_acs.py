from __future__ import annotations

from typing import Any

from azure.communication.email import EmailClient


def send_email_via_acs(
    connection_string: str,
    sender: str,
    recipients: list[str],
    subject: str,
    html_content: str,
    logger: Any,
) -> None:
    if not connection_string or not sender:
        raise ValueError("ACS email settings are not complete")
    if not recipients:
        raise ValueError("no email recipients")

    client = EmailClient.from_connection_string(connection_string)
    message = {
        "senderAddress": sender,
        "recipients": {
            "to": [{"address": address} for address in recipients],
        },
        "content": {
            "subject": subject,
            "html": html_content,
        },
    }

    poller = client.begin_send(message)
    result = poller.result()
    logger.info("email_sent", extra={"backend": "acs", "result": str(result)})
