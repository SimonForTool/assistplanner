"""Rozesílání upozornění: e-mail (SMTP), SMS (Twilio), Telegram a obecný webhook.

Kanály bez konfigurace v .env se přeskakují a zpráva se jen zaloguje (zkušební režim),
takže aplikace funguje i bez nich. Chyby odesílání se překládají do srozumitelných
českých hlášek, které se uživateli zobrazí (např. při zkušební zprávě v „Moje kontakty“).
"""
import logging
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import requests

import config

log = logging.getLogger(__name__)


class DeliveryError(RuntimeError):
    """Odeslání selhalo; zpráva je určená uživateli."""


# --- E-mail (SMTP) ---

def _smtp_security() -> str:
    """'ssl' (port 465), 'starttls' (587, výchozí) nebo 'none' – lze vynutit SMTP_SECURITY."""
    if config.SMTP_SECURITY in ("ssl", "starttls", "none"):
        return config.SMTP_SECURITY
    return "ssl" if config.SMTP_PORT == 465 else "starttls"


def _sender() -> str:
    address = config.SMTP_FROM or config.SMTP_USER
    return formataddr((config.SMTP_FROM_NAME, address)) if config.SMTP_FROM_NAME else address


def deliver_email(to: str, subject: str, text: str,
                  attachments: list[tuple[bytes, str, str, str]] | None = None) -> None:
    """Odešle e-mail. attachments: (data, maintype, subtype, filename). Bez SMTP jen zaloguje."""
    if not config.email_enabled():
        log.info("[MOCK e-mail → %s] %s\n%s", to, subject, text)
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _sender()
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain=(config.SMTP_FROM or config.SMTP_USER or "syncho").split("@")[-1])
    msg.set_content(text)
    for data, maintype, subtype, filename in attachments or []:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)

    security = _smtp_security()
    host, port = config.SMTP_HOST, config.SMTP_PORT
    try:
        if security == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(host, port, timeout=20)
        with smtp:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if config.SMTP_USER:
                smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise DeliveryError(
            "Přihlášení k e-mailovému serveru selhalo – zkontrolujte SMTP_USER a SMTP_PASSWORD "
            "(u Gmailu a Seznamu je potřeba „heslo aplikace“, ne běžné heslo)."
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise DeliveryError(f"Server odmítl adresu příjemce {to}.") from exc
    except smtplib.SMTPSenderRefused as exc:
        raise DeliveryError(
            f"Server odmítl odesílatele {config.SMTP_FROM or config.SMTP_USER} – SMTP_FROM musí "
            "obvykle odpovídat přihlášenému účtu (SMTP_USER)."
        ) from exc
    except (socket.gaierror, ConnectionRefusedError, TimeoutError, socket.timeout, OSError) as exc:
        raise DeliveryError(
            f"Nelze se připojit k {host}:{port} ({exc.__class__.__name__}). Zkontrolujte SMTP_HOST "
            "a SMTP_PORT. Bezplatný účet PythonAnywhere povoluje odchozí poštu jen přes vybrané "
            "servery (spolehlivě smtp.gmail.com)."
        ) from exc
    except smtplib.SMTPException as exc:
        raise DeliveryError(f"E-mailový server vrátil chybu: {exc}") from exc


# --- SMS (Twilio) ---

def normalize_phone(phone: str) -> str:
    """„724 528 278“ → „+420724528278“; mezinárodní čísla nechá (jen bez mezer a pomlček)."""
    p = re.sub(r"[\s\-/().]", "", phone or "")
    if p.startswith("00"):
        p = "+" + p[2:]
    if re.fullmatch(r"\d{9}", p):
        p = "+420" + p
    return p


_TWILIO_HINTS = {
    20003: "Twilio odmítl přihlášení – zkontrolujte TWILIO_ACCOUNT_SID a TWILIO_AUTH_TOKEN.",
    21211: "Telefonní číslo příjemce není platné – zadejte ho ve tvaru +420…",
    21408: "Twilio nemá povolené posílání SMS do této země – v konzoli Twilio zapněte "
           "Messaging → Geo permissions → Czech Republic.",
    21606: "TWILIO_FROM není číslo vašeho účtu Twilio, ze kterého lze posílat SMS.",
    21608: "Účet Twilio je ve zkušební verzi a smí posílat jen na ověřená čísla – číslo příjemce "
           "přidejte v Twilio v části Verified Caller IDs, nebo účet dobijte.",
    21610: "Příjemce odhlásil SMS z tohoto čísla (odpověděl STOP).",
    21612: "Na toto číslo nelze z vašeho čísla Twilio posílat SMS.",
}


def deliver_sms(phone: str, text: str) -> None:
    """Odešle SMS přes Twilio. Bez nastavení Twilio jen zaloguje."""
    to = normalize_phone(phone)
    text = text[:320]
    if not config.sms_enabled():
        log.info("[MOCK SMS → %s] %s", to, text)
        return
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{config.TWILIO_ACCOUNT_SID}/Messages.json",
            data={"To": to, "From": config.TWILIO_FROM, "Body": text},
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            timeout=20,
        )
    except requests.RequestException as exc:
        raise DeliveryError(
            f"Nelze se spojit s Twilio ({exc.__class__.__name__}). Na PythonAnywhere ověřte, "
            "že je api.twilio.com dostupné."
        ) from exc
    if resp.status_code >= 400:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        code = body.get("code")
        raise DeliveryError(_TWILIO_HINTS.get(code) or f"Twilio {resp.status_code}: "
                            f"{body.get('message') or resp.text[:200]}")


# --- Společné kanály (Telegram, webhook, e-mail na NOTIFY_EMAIL_TO) ---

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


def notify(subject: str, text: str) -> dict[str, str]:
    """Odešle zprávu všemi nakonfigurovanými společnými kanály. Vrací {kanál: 'ok' | chyba}."""
    channels = []
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        channels.append(("telegram", lambda: _send_telegram(f"<b>{subject}</b>\n{text}")))
    if config.NOTIFY_WEBHOOK_URL:
        channels.append(("webhook", lambda: _send_webhook(f"{subject}\n{text}")))
    if config.email_enabled() and config.NOTIFY_EMAIL_TO:
        channels.append(("email", lambda: deliver_email(config.NOTIFY_EMAIL_TO, subject, text)))

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


# --- Upozornění na konkrétní úkol (e-mail s událostí do kalendáře, SMS) ---

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
        return (v or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

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
    attachments = []
    if task.due_date and event != "Úkol smazán":
        attachments.append((_ics(task), "text", "calendar", f"{task.code}.ics"))
    deliver_email(to, subject, "\n".join(body), attachments)


def send_task_sms(phone: str, task, event: str) -> None:
    from utils.helpers import fmt_dt
    text = f"Syncho – {event}: {task.title} ({fmt_dt(task.due_date)})"
    if task.location:
        text += f", {task.location}"
    deliver_sms(phone, text)


# --- Zkušební zpráva ---

def send_test(email: str | None, phone: str | None) -> dict[str, str]:
    """Pošle zkušební e-mail / SMS. Vrací {kanál: 'odesláno' | 'zkušební režim' | chyba}."""
    results = {}
    text = "Toto je zkušební zpráva z aplikace Syncho – Assistant Planner. Odesílání funguje."
    for kind, target, enabled, send in (
        ("e-mail", email, config.email_enabled(), lambda: deliver_email(email, "Syncho – zkušební e-mail", text)),
        ("SMS", phone, config.sms_enabled(), lambda: deliver_sms(phone, "Syncho: zkušební SMS. Odesílání funguje.")),
    ):
        if not target:
            results[kind] = "není vyplněno"
        elif not enabled:
            results[kind] = "na serveru není nastaveno (jen zkušební režim)"
        else:
            try:
                send()
                results[kind] = "odesláno"
            except DeliveryError as exc:
                results[kind] = str(exc)
            except Exception as exc:
                results[kind] = f"nečekaná chyba: {exc}"
    return results
