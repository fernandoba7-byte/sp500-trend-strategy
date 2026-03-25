"""
Notification system for signal changes.

Supports Telegram and email channels.
"""

import os
import logging
import smtplib
from email.mime.text import MIMEText

import requests

logger = logging.getLogger(__name__)


def send_telegram(message: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Send a message via Telegram bot."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat:
        logger.warning("Telegram credentials not configured, skipping alert")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": message, "parse_mode": "Markdown"}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info("Telegram message sent successfully")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram message: {e}")
        return False


def send_email(
    subject: str,
    body: str,
    smtp_server: str | None = None,
    sender: str | None = None,
    recipient: str | None = None,
    password: str | None = None,
) -> bool:
    """Send an email alert."""
    smtp_server = smtp_server or "smtp.gmail.com"
    sender = sender or os.environ.get("EMAIL_SENDER")
    recipient = recipient or os.environ.get("EMAIL_RECIPIENT")
    password = password or os.environ.get("EMAIL_PASSWORD")

    if not sender or not recipient or not password:
        logger.warning("Email credentials not configured, skipping alert")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient

    try:
        with smtplib.SMTP_SSL(smtp_server, 465, timeout=10) as server:
            server.login(sender, password)
            server.send_message(msg)
        logger.info("Email sent successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False


def send_alert(message: str, config: dict) -> None:
    """
    Send alert via all configured channels.

    Args:
        message: Alert message text.
        config: alerts section from config.yaml.
    """
    channels = config.get("channels", [])

    if "telegram" in channels:
        tg_config = config.get("telegram", {})
        send_telegram(
            message,
            bot_token=tg_config.get("bot_token"),
            chat_id=tg_config.get("chat_id"),
        )

    if "email" in channels:
        email_config = config.get("email", {})
        send_email(
            subject="SP500 Strategy Signal Alert",
            body=message,
            smtp_server=email_config.get("smtp_server"),
            sender=email_config.get("sender"),
            recipient=email_config.get("recipient"),
            password=email_config.get("password"),
        )
