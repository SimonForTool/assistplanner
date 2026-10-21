"""Rozesílání upozornění přes Telegram, obecný webhook a e-mail.

Kanály bez konfigurace se přeskakují; pokud není nastaven žádný, zpráva se jen
zaloguje (mock režim).
"""
import logging
import smtplib
from email.message import EmailMessage

import requests

import config

log = logging.getLogger(__name__)


def _send_telegram(text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
        timeout=10,
    )
    resp.raise_for_status()


def _send_webhook(text: str) -> None:
    resp = requests.post(config.NOTIFY_WEBHOOK_URL, json={"text": text}, timeout=10)
    resp.raise_for_status()


def _send_email(subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM or config.SMTP_USER
    msg["To"] = config.NOTIFY_EMAIL_TO
    msg.set_content(text)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def notify(subject: str, text: str) -> dict[str, str]:
    """Odešle zprávu všemi nakonfigurovanými kanály. Vrací {kanál: 'ok' | chyba}."""
    channels = []
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        channels.append(("telegram", lambda: _send_telegram(f"<b>{subject}</b>\n{text}")))
    if config.NOTIFY_WEBHOOK_URL:
        channels.append(("webhook", lambda: _send_webhook(f"{subject}\n{text}")))
    if config.SMTP_HOST and config.NOTIFY_EMAIL_TO:
        channels.append(("email", lambda: _send_email(subject, text)))

    if not channels:
        log.info("[MOCK notifikace] %s – %s", subject, text)
        return {"mock": "ok"}

    results = {}
    for name, send in channels:
        try:
            send()
            results[name] = "ok"
        except Exception as exc:  # jeden selhávající kanál nesmí shodit ostatní
            log.warning("Notifikace přes %s selhala: %s", name, exc)
            results[name] = str(exc)
    return results
