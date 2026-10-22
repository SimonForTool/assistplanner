"""Kalendář: měsíční přehled a úkoly vybraného dne (minulé i budoucí)."""
import calendar as pycal
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, render_template, request

from routes.auth import login_required
from services import task_service
from utils import czech_calendar as cz
from utils.helpers import now_local

bp = Blueprint("calendar", __name__)


def _parse_day(value: str | None, fallback: date) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else fallback
    except ValueError:
        return fallback


def _shift_month(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, pycal.monthrange(year, month)[1]))


def tasks_by_day(tasks) -> dict[date, list]:
    days = defaultdict(list)
    for t in tasks:
        if t.due_date:
            days[t.due_date.date()].append(t)
    for items in days.values():
        items.sort(key=lambda t: t.due_date)
    return days


def day_info(d: date, today: date) -> dict:
    return {
        "date": d,
        "is_today": d == today,
        "is_past": d < today,
        "day_off": cz.is_day_off(d),
        "holiday": cz.holiday(d),
        "nameday": cz.nameday(d),
        "weekday_short": cz.WEEKDAYS_SHORT[d.weekday()],
    }


@bp.route("/calendar")
@login_required
def index():
    today = now_local().date()
    selected = _parse_day(request.args.get("d"), today)
    by_day = tasks_by_day(task_service.list_tasks())

    # Mřížka měsíce od pondělí do neděle (včetně přesahu z vedlejších měsíců)
    first = selected.replace(day=1)
    start = first - timedelta(days=first.weekday())
    weeks = []
    cursor = start
    while True:
        week = []
        for _ in range(7):
            info = day_info(cursor, today)
            info["in_month"] = cursor.month == selected.month
            info["tasks"] = by_day.get(cursor, [])
            week.append(info)
            cursor += timedelta(days=1)
        weeks.append(week)
        if cursor.month != selected.month and cursor > first:
            break

    day_tasks = by_day.get(selected, [])
    return render_template(
        "calendar.html",
        weeks=weeks,
        selected=day_info(selected, today),
        day_tasks=day_tasks,
        month_label=f"{cz.MONTHS[selected.month - 1].capitalize()} {selected.year}",
        prev_month=_shift_month(selected, -1),
        next_month=_shift_month(selected, 1),
        prev_day=selected - timedelta(days=1),
        next_day=selected + timedelta(days=1),
        today=today,
        weekdays=cz.WEEKDAYS_SHORT,
        long_date=cz.fmt_long(selected),
    )
