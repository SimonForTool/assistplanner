"""Formátování, práce s daty a pomocné funkce pro šablony."""
from datetime import date, datetime, time, timedelta, timezone

import config
from models import Priority, TaskStatus

# Bootstrap 5 barvy odznaků
PRIORITY_BADGES = {
    Priority.LOW: "secondary",
    Priority.MEDIUM: "primary",
    Priority.HIGH: "warning",
    Priority.URGENT: "danger",
}
STATUS_BADGES = {
    TaskStatus.OPEN: "primary",
    TaskStatus.IN_PROGRESS: "warning",
    TaskStatus.CLOSED: "success",
    TaskStatus.CANCELLED: "secondary",
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
