"""Formátování, práce s daty a stav Streamlit session."""
from datetime import date, datetime, time, timedelta, timezone

import streamlit as st

import config
from database.models import Priority, TaskStatus, UserRole

PRIORITY_COLORS = {
    Priority.LOW: "#6c757d",
    Priority.MEDIUM: "#0d6efd",
    Priority.HIGH: "#fd7e14",
    Priority.URGENT: "#dc3545",
}
STATUS_COLORS = {
    TaskStatus.OPEN: "#0d6efd",
    TaskStatus.IN_PROGRESS: "#fd7e14",
    TaskStatus.CLOSED: "#198754",
    TaskStatus.CANCELLED: "#6c757d",
}
PRIORITY_ICONS = {
    Priority.LOW: "⚪",
    Priority.MEDIUM: "🔵",
    Priority.HIGH: "🟠",
    Priority.URGENT: "🔴",
}
STATUS_ICONS = {
    TaskStatus.OPEN: "🆕",
    TaskStatus.IN_PROGRESS: "⏳",
    TaskStatus.CLOSED: "✅",
    TaskStatus.CANCELLED: "🚫",
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


# --- Odznaky ---

def badge(text: str, color: str) -> str:
    return (f"<span style='background:{color};color:#fff;padding:2px 8px;"
            f"border-radius:10px;font-size:0.8em;white-space:nowrap'>{text}</span>")


def priority_badge(p: Priority) -> str:
    return badge(p.value, PRIORITY_COLORS[p])


def status_badge(s: TaskStatus) -> str:
    return badge(s.value, STATUS_COLORS[s])


def priority_label(p: Priority) -> str:
    return f"{PRIORITY_ICONS[p]} {p.value}"


def status_label(s: TaskStatus) -> str:
    return f"{STATUS_ICONS[s]} {s.value}"


# --- Session state ---

def current_user() -> UserRole | None:
    return st.session_state.get("user_role")


def flash(message: str, kind: str = "success") -> None:
    """Zpráva zobrazená po st.rerun()."""
    st.session_state.setdefault("_flash", []).append((kind, message))


def show_flashes() -> None:
    for kind, msg in st.session_state.pop("_flash", []):
        getattr(st, kind)(msg)
