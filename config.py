"""Konfigurace aplikace načítaná z proměnných prostředí (.env)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# --- Aplikace ---
APP_NAME = "Syncho"
APP_TAGLINE = "Assistant Planner"
# Zobrazovaná jména profilů (role zůstávají: náměstek / asistentka)
DEPUTY_NAME = _env("DEPUTY_NAME", "Michal") or "Michal"
ASSISTANT_NAME = _env("ASSISTANT_NAME", "Hanka") or "Hanka"

# Organizace úkolu a jejich podkategorie (prázdný seznam = bez podkategorií)
ORGANIZATIONS = {
    "VFN": ["AI", "NIS", "Ostatní"],
    "ONMB": [],
    "MZČR": [],
    "FNKV": [],
}

# Upozornění asistentce na úkoly, které zadá náměstek (u úkolu lze vypnout)
# Výchozí kontakty pro upozornění (každý je může změnit v aplikaci: Moje kontakty)
ASSISTANT_EMAIL = _env("ASSISTANT_EMAIL")
ASSISTANT_PHONE = _env("ASSISTANT_PHONE")
DEPUTY_EMAIL = _env("DEPUTY_EMAIL")
DEPUTY_PHONE = _env("DEPUTY_PHONE")


def _secret_key() -> str:
    """SECRET_KEY z .env, jinak náhodný klíč uložený v souboru (přežije restart serveru)."""
    key = _env("SECRET_KEY")
    if key:
        return key
    path = BASE_DIR / ".secret_key"
    if not path.exists():
        import secrets
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


SECRET_KEY = _secret_key()
DEPUTY_PASSWORD = _env("DEPUTY_PASSWORD")
ASSISTANT_PASSWORD = _env("ASSISTANT_PASSWORD")
DATABASE_URL = _env("DATABASE_URL", f"sqlite:///{BASE_DIR / 'assistplanner.db'}")
TIMEZONE = ZoneInfo(_env("APP_TIMEZONE", "Europe/Prague"))
SEED_DEMO_DATA = _env("SEED_DEMO_DATA", "1") == "1"
AGING_DAYS = 7
# Max. velikost nahrávky / uploadu (Whisper přijme nejvýše 25 MB)
MAX_UPLOAD_MB = 25

# --- OpenAI ---
OPENAI_API_KEY = _env("OPENAI_API_KEY")
OPENAI_MODEL = _env("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TRANSCRIBE_MODEL = _env("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

# --- Microsoft Graph ---
MS_TENANT_ID = _env("MS_TENANT_ID")
MS_CLIENT_ID = _env("MS_CLIENT_ID")
MS_CLIENT_SECRET = _env("MS_CLIENT_SECRET")
MS_DEPUTY_MAILBOX = _env("MS_DEPUTY_MAILBOX")
MS_ASSISTANT_MAILBOX = _env("MS_ASSISTANT_MAILBOX")
CALENDAR_EVENT_MINUTES = int(_env("CALENDAR_EVENT_MINUTES", "60") or 60)

# --- Google kalendář (Google Apps Script, viz google_apps_script/Syncho.gs) ---
GCAL_SCRIPT_URL = _env("GCAL_SCRIPT_URL")
GCAL_SECRET = _env("GCAL_SECRET")
GCAL_CALENDAR_NAME = _env("GCAL_CALENDAR_NAME")  # jen pro zobrazení, např. hana.gartn@gmail.com
# Kopie e-mailu o každém pracovním úkolu (čárkou oddělené adresy), např. sdílená schránka asistentky
TASK_EMAIL_COPY = [a.strip() for a in _env("TASK_EMAIL_COPY").split(",") if a.strip()]
# Hosté zvaní automaticky k nové události (čárkou oddělené e-maily); prázdné = zve se ručně
GCAL_GUESTS = [g.strip() for g in _env("GCAL_GUESTS").split(",") if g.strip()]

# --- SMS (Twilio) ---
TWILIO_ACCOUNT_SID = _env("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _env("TWILIO_AUTH_TOKEN")
TWILIO_FROM = _env("TWILIO_FROM")

# --- Notifikace ---
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
NOTIFY_WEBHOOK_URL = _env("NOTIFY_WEBHOOK_URL")
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", "587") or 587)
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM = _env("SMTP_FROM")
SMTP_FROM_NAME = _env("SMTP_FROM_NAME", "Syncho")
# ssl (port 465) / starttls (port 587) / none; prázdné = podle portu
SMTP_SECURITY = _env("SMTP_SECURITY").lower()
# Příloha .ics (událost do kalendáře) v e-mailu s úkolem; výchozí vypnuto – údaje se zapisují ručně
EMAIL_ATTACH_ICS = _env("EMAIL_ATTACH_ICS", "0") == "1"
# Veřejná adresa aplikace pro odkaz v e-mailu (prázdné = zjistí se z požadavku)
APP_URL = _env("APP_URL").rstrip("/")
NOTIFY_EMAIL_TO = _env("NOTIFY_EMAIL_TO")


def openai_enabled() -> bool:
    return bool(OPENAI_API_KEY)


def graph_enabled() -> bool:
    return all([MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET])


def smtp_enabled() -> bool:
    return bool(SMTP_HOST and (SMTP_FROM or SMTP_USER))


def email_enabled() -> bool:
    """E-mail lze odeslat přes SMTP, nebo přes Google účet skriptu Apps Script."""
    return smtp_enabled() or gcal_enabled()


def email_via() -> str:
    if smtp_enabled():
        return f"{SMTP_HOST}:{SMTP_PORT}"
    if gcal_enabled():
        from services import gcal_service
        return f"Google účet {gcal_service.calendar_name() or '(Apps Script)'}"
    return ""


def sms_enabled() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM])


def gcal_enabled() -> bool:
    """Google kalendář propojen (adresa skriptu + klíč z aplikace nebo z .env)."""
    from services import gcal_service
    return gcal_service.is_configured()
