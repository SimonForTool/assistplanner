"""Google kalendář přes webovou aplikaci Google Apps Script (google_apps_script/Syncho.gs).

Skript běží v Google účtu, do jehož kalendáře se zapisuje (např. soukromý Gmail asistentky).
Aplikace mu posílá JSON s tajným klíčem; skript událost vytvoří, upraví nebo zruší přes
Google Calendar API, takže změny a zrušení dostanou i pozvaní hosté (např. v Outlooku).
Bez GCAL_SCRIPT_URL běží zkušební režim: nic se neodesílá a události dostanou ID „mock-…“.
"""
import logging
import uuid
from datetime import timedelta

import requests

import config

log = logging.getLogger(__name__)
MOCK_PREFIX = "mock-"


class GCalError(RuntimeError):
    """Chyba zápisu do Google kalendáře; zpráva je určená uživateli."""


def _call(payload: dict) -> dict:
    try:
        # Apps Script odpovídá přesměrováním na script.googleusercontent.com – requests ho následuje
        resp = requests.post(config.GCAL_SCRIPT_URL, json={"secret": config.GCAL_SECRET, **payload},
                             timeout=30)
    except requests.RequestException as exc:
        raise GCalError(
            f"Nelze se spojit s Google Apps Script ({exc.__class__.__name__}). Na bezplatném "
            "PythonAnywhere ověřte, že jsou script.google.com a script.googleusercontent.com povolené."
        ) from exc
    try:
        data = resp.json()
    except ValueError as exc:
        hint = ("Skript není nasazený pro přístup „Kdokoli“ (Anyone), nebo je GCAL_SCRIPT_URL špatně."
                if "accounts.google.com" in resp.url or resp.status_code in (401, 403, 404)
                else f"Odpověď {resp.status_code} není JSON.")
        raise GCalError(f"Google Apps Script neodpověděl správně – {hint}") from exc
    if not data.get("ok"):
        error = data.get("error", "neznámá chyba")
        if error == "neznámá akce":
            error = ("skript v Google účtu je starší verze – vložte aktuální google_apps_script/Syncho.gs "
                     "a nasaďte novou verzi (Implementovat → Spravovat implementace → upravit → Nová verze)")
        elif error == "unauthorized":
            error = "nesouhlasí tajný klíč – GCAL_SECRET v .env musí být stejný jako SECRET ve skriptu"
        raise GCalError(f"Google kalendář: {error}")
    return data


def _event_payload(task) -> dict:
    from services.notify_service import _task_lines

    start = task.due_date
    end = start + timedelta(minutes=config.CALENDAR_EVENT_MINUTES)
    description = "\n".join(_task_lines(task)[1:])  # bez první řádky (název je v předmětu)
    if config.APP_URL:
        description += f"\n\nÚkol v aplikaci: {config.APP_URL}/tasks/{task.id}"
    return {
        "title": task.title,
        "start": start.strftime("%Y-%m-%dT%H:%M:%S"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%S"),
        "timeZone": str(config.TIMEZONE),
        "location": task.location or "",
        "description": description,
        "guests": config.GCAL_GUESTS,
    }


def upsert_event(task) -> str:
    """Vytvoří nebo aktualizuje událost úkolu, vrátí její ID."""
    event_id = task.gcal_event_id
    if not config.gcal_enabled():
        if event_id:
            log.info("[MOCK Google kalendář] Aktualizována událost %s", event_id)
            return event_id
        event_id = f"{MOCK_PREFIX}{uuid.uuid4().hex[:12]}"
        log.info("[MOCK Google kalendář] Vytvořena událost %s: %s", event_id, task.title)
        return event_id
    payload = {"action": "upsert", **_event_payload(task)}
    if event_id and not event_id.startswith(MOCK_PREFIX):
        payload["eventId"] = event_id
    return _call(payload)["eventId"]


def delete_event(event_id: str) -> None:
    if not config.gcal_enabled() or event_id.startswith(MOCK_PREFIX):
        log.info("[MOCK Google kalendář] Smazána událost %s", event_id)
        return
    _call({"action": "delete", "eventId": event_id})


SCRIPT_VERSION = 2  # verze google_apps_script/Syncho.gs, kterou aplikace potřebuje


def ping() -> str:
    """Ověří spojení se skriptem; vrátí název kalendáře (a upozorní na starou verzi skriptu)."""
    if not config.gcal_enabled():
        raise GCalError("Google kalendář není nastaven (GCAL_SCRIPT_URL a GCAL_SECRET v .env).")
    data = _call({"action": "ping"})
    name = data.get("calendar", "?")
    version = data.get("version") or 1
    if version < SCRIPT_VERSION:
        raise GCalError(
            f"Kalendář „{name}“ je připojen, ale adresa v GCAL_SCRIPT_URL vede na starou verzi skriptu "
            f"(verze {version}, potřeba {SCRIPT_VERSION}). Buď v Google vydejte novou verzi té implementace, "
            "nebo do .env zkopírujte adresu implementace, kterou jste aktualizoval(a)."
        )
    return f"{name} · skript verze {version}"


def send_mail(to: str, subject: str, text: str) -> None:
    """Odešle e-mail z Google účtu skriptu (MailApp) – bez nastavování SMTP."""
    _call({"action": "mail", "to": to, "subject": subject, "body": text, "name": config.SMTP_FROM_NAME})
