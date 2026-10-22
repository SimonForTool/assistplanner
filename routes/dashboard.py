"""Hlavní přehled: KPI, ranní AI briefing, tabulka úkolů s filtry a export."""
import csv
import io
import re
from datetime import date, timedelta

from flask import Blueprint, Response, jsonify, render_template, request
from markupsafe import Markup, escape

import config
from models import Priority, Task, TaskStatus, TaskType, UserRole
from routes.auth import login_required
from services import ai_service, task_service
from services.outlook_service import get_outlook
from utils import czech_calendar as cz
from utils.helpers import ACTIVE_STATUSES, enum_by_name, fmt_dt, now_local, today_bounds

bp = Blueprint("dashboard", __name__)

# Briefing se generuje nejvýše jednou denně na proces (lze vynutit tlačítkem)
_briefing_cache: dict[date, tuple[str, bool]] = {}


def parse_filters(args, default_active: bool = True) -> dict:
    """Filtry z query stringu. Bez odeslaného formuláře se zobrazí jen aktivní úkoly."""
    statuses = [s for s in (enum_by_name(TaskStatus, v) for v in args.getlist("status")) if s]
    if not statuses and "f" not in args and default_active:
        statuses = list(ACTIVE_STATUSES)
    return {
        "search": args.get("q", ""),
        "statuses": statuses,
        "priorities": [p for p in (enum_by_name(Priority, v) for v in args.getlist("priority")) if p],
        "creators": [c for c in (enum_by_name(UserRole, v) for v in args.getlist("creator")) if c],
    }


def kpis(tasks: list[Task]) -> dict:
    start, end = today_bounds()
    active = [t for t in tasks if t.status in ACTIVE_STATUSES]
    return {
        "due_today": sum(1 for t in active if t.due_date and start <= t.due_date < end),
        "overdue": sum(1 for t in active if task_service.is_overdue(t)),
        "aging": sum(1 for t in active if task_service.is_aging(t, config.AGING_DAYS)),
        "hot": sum(1 for t in active if t.priority in (Priority.HIGH, Priority.URGENT)),
    }


@bp.route("/")
@login_required
def index():
    from routes.calendar import day_info, tasks_by_day

    tasks = task_service.list_tasks()
    filters = parse_filters(request.args)
    filtered = task_service.filter_tasks(tasks, **filters)
    now = now_local()
    today = now.date()
    by_day = tasks_by_day(t for t in tasks if t.status in ACTIVE_STATUSES)
    strip = []
    for offset in range(-3, 11):  # 3 dny zpět, 10 dní dopředu
        d = today + timedelta(days=offset)
        info = day_info(d, today)
        info["count"] = len(by_day.get(d, []))
        strip.append(info)
    return render_template(
        "dashboard.html", tasks=filtered, kpis=kpis(tasks), filters=filters, today=now,
        greeting=cz.greeting(now), long_date=cz.fmt_long(today),
        nameday=cz.nameday_sentence(today), holiday=cz.holiday(today),
        tomorrow_nameday=cz.nameday(today + timedelta(days=1)), strip=strip,
    )


def _briefing_html(text: str) -> Markup:
    """Bezpečný převod jednoduchého Markdownu (odrážky, **tučně**) na HTML."""
    items = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        html = str(escape(re.sub(r"^(?:[-•*]|\d+[.)])\s+", "", line)))
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        items.append(f"<li>{html}</li>")
    return Markup(f"<ul class='mb-0'>{''.join(items)}</ul>")


@bp.route("/api/briefing")
@login_required
def briefing():
    today = now_local().date()
    if request.args.get("refresh") or today not in _briefing_cache:
        active = task_service.list_tasks(include_inactive=False)
        calendar, warning = [], None
        try:
            calendar = get_outlook().list_events_today(UserRole.DEPUTY)
        except Exception as exc:
            warning = f"Kalendář nedostupný: {exc}"
        text, ai_used = ai_service.generate_morning_briefing(active, calendar)
        _briefing_cache.clear()
        _briefing_cache[today] = (text, ai_used)
        if warning:
            return jsonify(html=_briefing_html(text), ai_used=ai_used, warning=warning)
    text, ai_used = _briefing_cache[today]
    return jsonify(html=_briefing_html(text), ai_used=ai_used)


# --- Export ---

EXPORT_COLUMNS = ["ID", "Název", "Typ", "Komu slíbeno", "Místo", "Priorita", "Stav",
                  "Termín", "Zadal(a)", "Popis"]


def _export_rows(tasks: list[Task]) -> list[list[str]]:
    return [[t.code, t.title, t.task_type.value, t.assignee_target or "", t.location or "",
             t.priority.value, t.status.value, fmt_dt(t.due_date) if t.due_date else "",
             t.creator.value, t.description or ""] for t in tasks]


def _tasks_for_export() -> tuple[list[Task], str]:
    tasks = task_service.list_tasks()
    filters = parse_filters(request.args)
    scope = request.args.get("scope")
    if scope == "commitments":
        filters["task_type"] = TaskType.COMMITMENT
    name = f"{'zavazky' if scope == 'commitments' else 'ukoly'}_{now_local():%Y%m%d}"
    return task_service.filter_tasks(tasks, **filters), name


@bp.route("/export.csv")
@login_required
def export_csv():
    tasks, name = _tasks_for_export()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(EXPORT_COLUMNS)
    writer.writerows(_export_rows(tasks))
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={name}.csv"})


@bp.route("/export.xlsx")
@login_required
def export_xlsx():
    from openpyxl import Workbook
    from openpyxl.styles import Font

    tasks, name = _tasks_for_export()
    wb = Workbook()
    ws = wb.active
    ws.title = "Úkoly"
    ws.append(EXPORT_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in _export_rows(tasks):
        ws.append(row)
    for col, width in zip("ABCDEFGHIJ", (11, 45, 22, 28, 22, 11, 11, 17, 12, 50)):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={name}.xlsx"})
