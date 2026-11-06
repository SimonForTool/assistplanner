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


# --- Upozornění asistentce na konkrétní úkol (e-mail s pozvánkou do kalendáře, SMS) ---

def _task_lines(task) -> list[str]:
    from utils.helpers import fmt_dt
    lines = [f"{task.code}: {task.title}", f"Termín: {fmt_dt(task.due_date)}"]
    if task.organization:
        lines.append("Organizace: " + task.organization + (f" / {task.subcategory}" if task.subcategory else ""))
    for label, value in (("Místo", task.location), ("Komu slíbeno", task.assignee_target),
                         ("Zadáno komu", task.delegated_to)):
        if value:
            lines.append(f"{label}: {value}")
    lines.append(f"Priorita: {task.priority.value} · Stav: {task.status.value}")
    if task.description:
        lines += ["", task.description]
    return lines


def _ics(task, cancel: bool = False) -> bytes:
    """Událost ve formátu iCalendar – v Outlooku ji lze jedním klepnutím přidat do kalendáře."""
    from datetime import datetime, timedelta, timezone

    def esc(v: str) -> str:
        return (v or "").replace("\\", "\\\\").replace(";", "\;").replace(",", "\\,").replace("\n", "\\n")

    start = task.due_date.replace(tzinfo=config.TIMEZONE).astimezone(timezone.utc)
    end = start + timedelta(minutes=config.CALENDAR_EVENT_MINUTES)
    fmt = "%Y%m%dT%H%M%SZ"
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Syncho//Assistant Planner//CS",
        f"METHOD:{'CANCEL' if cancel else 'PUBLISH'}", "BEGIN:VEVENT",
        f"UID:syncho-task-{task.id}@syncho", f"DTSTAMP:{datetime.now(timezone.utc).strftime(fmt)}",
        f"DTSTART:{start.strftime(fmt)}", f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{esc(task.title)}", f"DESCRIPTION:{esc(chr(10).join(_task_lines(task)))}",
    ]
    if task.location:
        lines.append(f"LOCATION:{esc(task.location)}")
    if cancel:
        lines.append("STATUS:CANCELLED")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def send_task_email(to: str, task, event: str, changes: str | None = None) -> None:
    subject = f"{event}: {task.code} {task.title}"
    body = _task_lines(task)
    if changes:
        body = [f"Změny: {changes}", ""] + body
    text = "\n".join(body)
    if not config.email_enabled():
        log.info("[MOCK e-mail → %s] %s\n%s", to, subject, text)
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SMTP_FROM or config.SMTP_USER
    msg["To"] = to
    msg.set_content(text)
    if task.due_date and event != "Úkol smazán":
        msg.add_attachment(_ics(task), maintype="text", subtype="calendar",
                           filename=f"{task.code}.ics")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(msg)


def send_task_sms(phone: str, task, event: str) -> None:
    from utils.helpers import fmt_dt
    text = f"Syncho – {event}: {task.title} ({fmt_dt(task.due_date)})"
    if task.location:
        text += f", {task.location}"
    text = text[:300]
    if not config.sms_enabled():
        log.info("[MOCK SMS → %s] %s", phone, text)
        return
    resp = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
        data={"To": phone.replace(" ", ""), "From": config.TWILIO_FROM, "Body": text},
        auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Twilio {resp.status_code}: {resp.text[:200]}")
