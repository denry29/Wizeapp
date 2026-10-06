"""Backend-only SMTP delivery for account verification and security alerts."""

from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """Raised when a configured email cannot be delivered."""


def send_email(recipient: str, subject: str, body: str) -> None:
    """Send a plain-text message using server-side SMTP settings."""
    if current_app.testing:
        current_app.extensions.setdefault("test_email_outbox", []).append({
            "to": recipient,
            "subject": subject,
            "body": body,
        })
        return

    host = current_app.config.get("EMAIL_HOST", "").strip()
    sender = current_app.config.get("EMAIL_FROM", "").strip()
    username = current_app.config.get("EMAIL_USERNAME", "").strip()
    password = current_app.config.get("EMAIL_PASSWORD", "")
    use_tls = current_app.config["EMAIL_USE_TLS"]
    use_ssl = current_app.config["EMAIL_USE_SSL"]
    if not host or not sender:
        raise EmailDeliveryError(
            "Email delivery is not configured. Set EMAIL_HOST and EMAIL_FROM "
            "on the Flask server.")
    if use_tls and use_ssl:
        raise EmailDeliveryError(
            "Configure either EMAIL_USE_TLS or EMAIL_USE_SSL, not both.")
    if bool(username) != bool(password):
        raise EmailDeliveryError(
            "Set both EMAIL_USERNAME and EMAIL_PASSWORD, or leave both empty.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(
                    host, current_app.config["EMAIL_PORT"],
                    timeout=current_app.config["EMAIL_TIMEOUT"],
                    context=ssl.create_default_context()) as smtp:
                _send(smtp, username, password, message)
        else:
            with smtplib.SMTP(
                    host, current_app.config["EMAIL_PORT"],
                    timeout=current_app.config["EMAIL_TIMEOUT"]) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                _send(smtp, username, password, message)
    except (OSError, smtplib.SMTPException) as error:
        logger.warning("Email delivery failed (%s).", type(error).__name__)
        raise EmailDeliveryError(
            "Email delivery failed. Check the server mail settings and try again."
        ) from None


def _send(smtp: smtplib.SMTP, username: str, password: str,
          message: EmailMessage) -> None:
    if username and password:
        smtp.login(username, password)
    smtp.send_message(message)
