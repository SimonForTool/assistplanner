"""Formátování, práce s daty a pomocné funkce pro šablony."""
from datetime import date, datetime, time, timedelta, timezone

import config
from models import Priority, TaskStatus

# CSS třídy odznaků (static/css/app.css: .tone-*)
PRIORITY_BADGES = {
    Priority.LOW: "muted",
    Priority.MEDIUM: "sky",
    Priority.HIGH: "amber",
    Priority.URGENT: "red",
}
STATUS_BADGES = {
    TaskStatus.OPEN: "navy",
    TaskStatus.IN_PROGRESS: "amber",
    TaskStatus.CLOSED: "green",
    TaskStatus.CANCELLED: "muted",
}
ACTIVE_STATUSES = (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)


# --- Datum a čas ---

def now_local() -> datetime:
    """Aktuální lokální čas bez tzinfo (stejně jako due_date v DB)."""
    return datetime.now(config.TIMEZONE).replace(tzinfo=None)


def utc_to_local(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(config.TIMEZONE).replace(tzinfo=None)


def today_bounds() -> tuple[datetime, datetime]:
    start = datetime.combine(now_local().date(), time.min)
    return start, start + timedelta(days=1)


def combine_date_time(d: date | None, t: time | None) -> datetime | None:
    if d is None:
        return None
    return datetime.combine(d, t or time(9, 0))


def fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.time() == time.min:
        return dt.strftime("%d.%m.%Y")
    return dt.strftime("%d.%m.%Y %H:%M")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def enum_by_name(enum_cls, name: str | None, default=None):
    """Bezpečný převod jména z formuláře (např. 'URGENT') na člen enumu."""
    try:
        return enum_cls[name] if name else default
    except KeyError:
        return default
