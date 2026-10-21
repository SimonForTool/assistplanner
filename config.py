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

# --- Notifikace ---
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")
NOTIFY_WEBHOOK_URL = _env("NOTIFY_WEBHOOK_URL")
SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = int(_env("SMTP_PORT", "587") or 587)
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
SMTP_FROM = _env("SMTP_FROM")
NOTIFY_EMAIL_TO = _env("NOTIFY_EMAIL_TO")


def openai_enabled() -> bool:
    return bool(OPENAI_API_KEY)


def graph_enabled() -> bool:
    return all([MS_TENANT_ID, MS_CLIENT_ID, MS_CLIENT_SECRET])
