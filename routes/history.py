"""Prohlížeč auditní stopy."""
import csv
import io

from flask import Blueprint, Response, render_template, request

from models import UserRole
from routes.auth import login_required
from services import task_service
from utils.helpers import enum_by_name, fmt_dt, now_local, utc_to_local

bp = Blueprint("history", __name__)


def _filtered():
    entries = task_service.get_history(limit=2000)
    search = request.args.get("q", "").strip().lower()
    user = enum_by_name(UserRole, request.args.get("user"))
    action = request.args.get("action", "")
    actions = sorted({h.action for h in entries})
    entries = [
        h for h in entries
        if (not user or h.user == user)
        and (not action or h.action == action)
        and (not search or search in f"{h.task_code} {h.task_title or ''} "
                                     f"{h.changes_summary or ''}".lower())
    ]
    return entries, actions


@bp.route("/history")
@login_required
def index():
    entries, actions = _filtered()
    return render_template("history.html", entries=entries, actions=actions, args=request.args)


@bp.route("/history.csv")
@login_required
def export_csv():
    entries, _ = _filtered()
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Čas", "Úkol", "Název", "Uživatel", "Akce", "Změny"])
    for h in entries:
        writer.writerow([fmt_dt(utc_to_local(h.timestamp)), h.task_code, h.task_title or "",
                         h.user.value, h.action, h.changes_summary or ""])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=historie_{now_local():%Y%m%d}.csv"})
