"""Doménová logika úkolů: CRUD s auditem, synchronizací kalendáře a notifikacemi.

UI volá výhradně tyto funkce, aby se žádná změna neobešla bez záznamu v TaskHistory.
"""
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import select

from models import Priority, Task, TaskHistory, TaskStatus, TaskType, UserRole, db, utcnow
from services import notify_service
from services.outlook_service import get_outlook
from utils.helpers import ACTIVE_STATUSES, fmt_dt, now_local

log = logging.getLogger(__name__)


@contextmanager
def get_session():
    """Transakce nad session Flask-SQLAlchemy (commit / rollback)."""
    try:
        yield db.session
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

EDITABLE_FIELDS = {
    "title": "Název",
    "description": "Popis",
    "task_type": "Typ",
    "assignee_target": "Komu slíbeno",
    "location": "Místo",
    "priority": "Priorita",
    "status": "Stav",
    "due_date": "Termín",
    "sync_deputy_cal": "Kalendář náměstka",
    "sync_assistant_cal": "Kalendář asistentky",
}
CALENDAR_FIELDS = ("title", "description", "location", "due_date")


def _fmt_value(value) -> str:
    if value is None or value == "":
        return "—"
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, datetime):
        return fmt_dt(value)
    if isinstance(value, bool):
        return "ano" if value else "ne"
    return str(value)


def _action_for(changed: set[str]) -> str:
    if changed == {"status"}:
        return "Změna stavu"
    if changed == {"due_date"}:
        return "Změna termínu"
    if changed == {"priority"}:
        return "Změna priority"
    return "Upraveno"


def _log(session, task: Task, user: UserRole, action: str, summary: str | None) -> None:
    session.add(TaskHistory(task_id=task.id, task_code=task.code, task_title=task.title,
                            user=user, action=action, changes_summary=summary))


# --- Outlook ---

def _calendar_slots(task: Task):
    return (
        (UserRole.DEPUTY, "sync_deputy_cal", "outlook_event_id_deputy"),
        (UserRole.ASSISTANT, "sync_assistant_cal", "outlook_event_id_assistant"),
    )


def _sync_calendar(task: Task, changed: set[str] | None = None) -> list[str]:
    """Uvede události v Outlooku do souladu s úkolem. Vrací seznam varování."""
    outlook = get_outlook()
    warnings = []
    for role, flag_attr, id_attr in _calendar_slots(task):
        wanted = getattr(task, flag_attr) and task.due_date and task.status in ACTIVE_STATUSES
        event_id = getattr(task, id_attr)
        try:
            if wanted and not event_id:
                setattr(task, id_attr, outlook.create_event(
                    role, task.title, task.due_date, task.description, task.location))
            elif wanted and event_id and changed and changed & set(CALENDAR_FIELDS):
                outlook.update_event(role, event_id, task.title, task.due_date,
                                     task.description, task.location)
            elif not wanted and event_id:
                outlook.delete_event(role, event_id)
                setattr(task, id_attr, None)
        except Exception as exc:
            log.warning("Synchronizace kalendáře (%s) selhala: %s", role.value, exc)
            warnings.append(f"Kalendář {role.value}: {exc}")
    return warnings


# --- Notifikace ---

def _notify_urgent(task: Task) -> None:
    notify_service.notify(
        "🔴 Urgentní úkol od asistentky",
        f"{task.code}: {task.title}\nTermín: {fmt_dt(task.due_date)}"
        + (f"\nMísto: {task.location}" if task.location else ""),
    )


def check_deadline_notifications() -> int:
    """Upozorní na závazky s termínem do 24 hodin (každý jen jednou). Vrací počet odeslaných."""
    now = now_local()
    sent = 0
    with get_session() as s:
        tasks = s.scalars(select(Task).where(
            Task.task_type == TaskType.COMMITMENT,
            Task.status.in_(ACTIVE_STATUSES),
            Task.due_date.is_not(None),
            Task.due_date >= now,
            Task.due_date <= now + timedelta(hours=24),
            Task.deadline_notified_at.is_(None),
        )).all()
        for t in tasks:
            target = f" ({t.assignee_target})" if t.assignee_target else ""
            notify_service.notify(
                "⏰ Závazek do 24 hodin",
                f"{t.code}: {t.title}{target}\nTermín: {fmt_dt(t.due_date)}",
            )
            t.deadline_notified_at = utcnow()
            sent += 1
    return sent


# --- CRUD ---

def list_tasks(include_inactive: bool = True) -> list[Task]:
    q = select(Task).order_by(Task.due_date.is_(None), Task.due_date, Task.id)
    if not include_inactive:
        q = q.where(Task.status.in_(ACTIVE_STATUSES))
    return list(db.session.scalars(q).all())


def get_task(task_id: int) -> Task | None:
    return db.session.get(Task, task_id)


def _apply_commitment_rule(data: dict) -> dict:
    """Vyplněné „Komu slíbeno“ = závazek (zobrazí se v „Co komu slíbil“)."""
    if (data.get("assignee_target") or "").strip():
        data = {**data, "task_type": TaskType.COMMITMENT}
    return data


def apply_commitment_rule_to_existing() -> int:
    """Jednorázově převede starší úkoly s vyplněným „Komu slíbeno“ na závazky. Vrací počet."""
    with get_session() as s:
        tasks = s.scalars(select(Task).where(
            Task.task_type == TaskType.STANDARD,
            Task.assignee_target.is_not(None),
            Task.assignee_target != "",
        )).all()
        for t in tasks:
            t.task_type = TaskType.COMMITMENT
            _log(s, t, t.creator, "Změna typu",
                 f"Typ: {TaskType.STANDARD.value} → {TaskType.COMMITMENT.value} "
                 "(automaticky – vyplněno „Komu slíbeno“)")
    return len(tasks)


def create_task(data: dict, user: UserRole) -> tuple[Task, list[str]]:
    data = _apply_commitment_rule(data)
    with get_session() as s:
        task = Task(creator=user, **{k: v for k, v in data.items() if k in EDITABLE_FIELDS})
        s.add(task)
        s.flush()
        warnings = _sync_calendar(task)
        details = [f"{label}: {_fmt_value(getattr(task, f))}"
                   for f, label in EDITABLE_FIELDS.items()
                   if getattr(task, f) not in (None, "", False)]
        _log(s, task, user, "Vytvořeno", "; ".join(details))
    if user == UserRole.ASSISTANT and task.priority == Priority.URGENT:
        _notify_urgent(task)
    return task, warnings


def update_task(task_id: int, data: dict, user: UserRole) -> tuple[Task | None, list[str]]:
    data = _apply_commitment_rule(data)
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None:
            return None, ["Úkol neexistuje."]
        changes, changed = [], set()
        for field, new in data.items():
            if field not in EDITABLE_FIELDS:
                continue
            old = getattr(task, field)
            if old != new:
                changes.append(f"{EDITABLE_FIELDS[field]}: {_fmt_value(old)} → {_fmt_value(new)}")
                changed.add(field)
                setattr(task, field, new)
        if not changed:
            return task, []
        if "due_date" in changed:
            task.deadline_notified_at = None
        warnings = _sync_calendar(task, changed)
        _log(s, task, user, _action_for(changed), "; ".join(changes))
    if ("priority" in changed and user == UserRole.ASSISTANT
            and task.priority == Priority.URGENT and task.status in ACTIVE_STATUSES):
        _notify_urgent(task)
    return task, warnings


def set_status(task_id: int, status: TaskStatus, user: UserRole) -> tuple[Task | None, list[str]]:
    return update_task(task_id, {"status": status}, user)


def delete_task(task_id: int, user: UserRole) -> list[str]:
    with get_session() as s:
        task = s.get(Task, task_id)
        if task is None:
            return ["Úkol neexistuje."]
        task.sync_deputy_cal = task.sync_assistant_cal = False
        warnings = _sync_calendar(task)
        _log(s, task, user, "Smazáno", f"Smazán úkol „{task.title}“ ({task.task_type.value})")
        s.flush()
        s.delete(task)
    return warnings


def get_history(task_id: int | None = None, limit: int = 500) -> list[TaskHistory]:
    q = select(TaskHistory).order_by(TaskHistory.timestamp.desc(), TaskHistory.id.desc())
    if task_id is not None:
        q = q.where(TaskHistory.task_id == task_id)
    return list(db.session.scalars(q.limit(limit)).all())


# --- Filtry a ukazatele (sdílí přehled, závazky a export) ---

def is_overdue(t: Task) -> bool:
    return t.status in ACTIVE_STATUSES and t.due_date is not None and t.due_date < now_local()


def is_aging(t: Task, days: int) -> bool:
    return t.status in ACTIVE_STATUSES and t.created_at < utcnow() - timedelta(days=days)


def filter_tasks(tasks: list[Task], search: str = "", statuses=(), priorities=(),
                 creators=(), task_type: TaskType | None = None) -> list[Task]:
    s = search.strip().lower()
    return [
        t for t in tasks
        if (not statuses or t.status in statuses)
        and (not priorities or t.priority in priorities)
        and (not creators or t.creator in creators)
        and (task_type is None or t.task_type == task_type)
        and (not s or s in " ".join(filter(None, [t.code, t.title, t.description,
                                                   t.assignee_target, t.location])).lower())
    ]


# --- Ukázková data ---

def seed_demo_data() -> bool:
    """Naplní prázdnou databázi několika ukázkovými úkoly. Vrací True, pokud plnila."""
    if db.session.scalar(select(Task.id).limit(1)) is not None:
        return False
    today = now_local().replace(second=0, microsecond=0)
    created_old = utcnow() - timedelta(days=10)
    demo = [
        Task(title="Porada vedení odboru", creator=UserRole.ASSISTANT,
             location="Zasedačka 3.12", priority=Priority.HIGH,
             due_date=today.replace(hour=10, minute=0)),
        Task(title="Poslat stanovisko k rozpočtu", task_type=TaskType.COMMITMENT,
             assignee_target="Ing. Novák (MF)", creator=UserRole.DEPUTY,
             priority=Priority.URGENT, due_date=today + timedelta(hours=20)),
        Task(title="Telefonát s hejtmanem", assignee_target="Hejtman kraje",
             creator=UserRole.ASSISTANT, due_date=today.replace(hour=14, minute=30)),
        Task(title="Podklady pro výbor", creator=UserRole.DEPUTY, priority=Priority.LOW,
             status=TaskStatus.IN_PROGRESS, due_date=today + timedelta(days=3),
             created_at=created_old),
        Task(title="Ozvat se ohledně dotačního programu", task_type=TaskType.COMMITMENT,
             assignee_target="Starostka Mgr. Dvořáková", creator=UserRole.DEPUTY,
             due_date=today - timedelta(days=1), created_at=created_old),
    ]
    with get_session() as s:
        s.add_all(demo)
        s.flush()
        for t in demo:
            _log(s, t, t.creator, "Vytvořeno", "Ukázková data")
    return True
