"""CRUD úkolů, rychlé šablony a hlasové / AI zadání."""
import logging
from datetime import timedelta

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for

import config
from models import Priority, TaskStatus, TaskType
from routes.auth import current_role, login_required, safe_next
from services import ai_service, czech_parser, task_service
from utils.helpers import enum_by_name, now_local, parse_dt

bp = Blueprint("tasks", __name__, url_prefix="/tasks")
log = logging.getLogger(__name__)


def _template(title: str, priority: Priority, days: int, hour: int, deputy_cal: bool) -> dict:
    due = (now_local() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"title": title, "task_type": TaskType.STANDARD, "priority": priority,
            "due_date": due, "sync_deputy_cal": deputy_cal}


TEMPLATES = {
    "schuzka": ("📅", "Schůzka", lambda: _template("Schůzka: ", Priority.MEDIUM, 1, 10, True)),
    "telefonat": ("📞", "Telefonát", lambda: _template("Telefonát: ", Priority.MEDIUM, 0, 14, False)),
    "podklady": ("📄", "Příprava podkladů",
                 lambda: _template("Příprava podkladů: ", Priority.HIGH, 3, 9, False)),
    "schvaleni": ("✍️", "Schválení", lambda: _template("Schválení: ", Priority.HIGH, 2, 9, False)),
}


def form_to_data(form, with_status: bool = False) -> dict:
    data = {
        "title": form.get("title", "").strip(),
        "task_type": enum_by_name(TaskType, form.get("task_type"), TaskType.STANDARD),
        "priority": enum_by_name(Priority, form.get("priority"), Priority.MEDIUM),
        "assignee_target": form.get("assignee_target", "").strip() or None,
        "location": form.get("location", "").strip() or None,
        "due_date": parse_dt(form.get("due_date")),
        "description": form.get("description", "").strip() or None,
        "sync_deputy_cal": form.get("sync_deputy_cal") == "on",
        "sync_assistant_cal": form.get("sync_assistant_cal") == "on",
    }
    if with_status:
        data["status"] = enum_by_name(TaskStatus, form.get("status"), TaskStatus.OPEN)
    return data


def _validate(data: dict) -> str | None:
    if not data["title"]:
        return "Vyplňte prosím název úkolu."
    if data["title"].endswith(":"):
        return "Doplňte prosím název za text šablony."
    return None


def _flash_warnings(warnings: list[str]) -> None:
    for w in warnings:
        flash(w, "warning")


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        data = form_to_data(request.form)
        error = _validate(data)
        if error:
            flash(error, "danger")
            return render_template("task_form.html", values=data, templates=TEMPLATES), 400
        task, warnings = task_service.create_task(data, current_role())
        _flash_warnings(warnings)
        flash(f"Úkol {task.code} byl uložen.", "success")
        return redirect(url_for("dashboard.index"))

    tpl = TEMPLATES.get(request.args.get("template", ""))
    values = tpl[2]() if tpl else {}
    if request.args.get("type") == "commitment":
        values["task_type"] = TaskType.COMMITMENT
    return render_template("task_form.html", values=values, templates=TEMPLATES)


@bp.route("/ai-extract", methods=["POST"])
@login_required
def ai_extract():
    """Přijme nahrávku (pole `audio`) nebo text (`text`) a vrátí předvyplněná pole formuláře.

    S OPENAI_API_KEY: Whisper + GPT. Bez klíče (nebo při chybě AI) se text rozebere
    pravidly v services/czech_parser.py; hlas pak přepisuje přímo prohlížeč.
    """
    audio = request.files.get("audio")
    text = request.form.get("text", "").strip()
    try:
        if audio and audio.filename is not None:
            content = audio.read()
            if content:
                text = ai_service.transcribe_audio(content, audio.filename or "nahravka.webm")
    except ai_service.AIUnavailable as exc:
        return jsonify(error=f"{exc} Použijte mikrofon v prohlížeči nebo napište text."), 400
    except Exception as exc:
        return jsonify(error=f"Přepis nahrávky selhal: {exc}"), 502
    if not text:
        return jsonify(error="Nahrávka ani text nebyly zadány."), 400

    ai_used = False
    result = None
    if config.openai_enabled():
        try:
            result = ai_service.extract_task(text)
            ai_used = True
        except Exception as exc:
            log.warning("AI strukturování selhalo, použita pravidla: %s", exc)
    if result is None:
        result = czech_parser.extract_task(text)

    due = parse_dt(result.get("due_date"))
    fields = {
        "title": result.get("title") or text[:80],
        "description": text,
        "task_type": next((t.name for t in TaskType if t.value == result.get("task_type")),
                          TaskType.STANDARD.name),
        "priority": next((p.name for p in Priority if p.value == result.get("priority")),
                         Priority.MEDIUM.name),
        "assignee_target": result.get("assignee_target") or "",
        "location": result.get("location") or "",
        "due_date": due.strftime("%Y-%m-%dT%H:%M") if due else "",
    }
    return jsonify(fields=fields, transcript=text, ai_used=ai_used)


def _get_or_404(task_id: int):
    task = task_service.get_task(task_id)
    if task is None:
        abort(404)
    return task


@bp.route("/<int:task_id>", methods=["GET", "POST"])
@login_required
def detail(task_id: int):
    task = _get_or_404(task_id)
    if request.method == "POST":
        data = form_to_data(request.form, with_status=True)
        # Šablonový název bez doplnění kontrolujeme jen při jeho změně
        error = _validate(data) if data["title"] != task.title else None
        if error:
            flash(error, "danger")
        else:
            _, warnings = task_service.update_task(task.id, data, current_role())
            _flash_warnings(warnings)
            flash(f"Úkol {task.code} byl upraven.", "success")
        return redirect(url_for("tasks.detail", task_id=task.id))
    values = {f: getattr(task, f) for f in task_service.EDITABLE_FIELDS}
    return render_template("task_detail.html", task=task, values=values,
                           history=task_service.get_history(task.id))


@bp.route("/<int:task_id>/status", methods=["POST"])
@login_required
def set_status(task_id: int):
    task = _get_or_404(task_id)
    status = enum_by_name(TaskStatus, request.form.get("status"))
    if status is None:
        abort(400)
    _, warnings = task_service.set_status(task.id, status, current_role())
    _flash_warnings(warnings)
    flash(f"{task.code}: stav změněn na „{status.value}“.", "success")
    return redirect(safe_next(request.form.get("next"), url_for("tasks.detail", task_id=task.id)))


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete(task_id: int):
    task = _get_or_404(task_id)
    code = task.code
    _flash_warnings(task_service.delete_task(task.id, current_role()))
    flash(f"Úkol {code} byl smazán.", "success")
    return redirect(url_for("dashboard.index"))
