"""SQLAlchemy modely: úkoly a jejich auditní historie."""
import enum
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    """Naivní UTC čas (SQLite neukládá časová pásma)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TaskType(enum.Enum):
    STANDARD = "Standardní úkol"
    COMMITMENT = "Závazek (Co komu slíbil)"


class Priority(enum.Enum):
    LOW = "Nízká"
    MEDIUM = "Střední"
    HIGH = "Vysoká"
    URGENT = "Urgentní"


class TaskStatus(enum.Enum):
    OPEN = "Otevřeno"
    IN_PROGRESS = "Probíhá"
    CLOSED = "Uzavřeno"
    CANCELLED = "Zrušeno"


class UserRole(enum.Enum):
    DEPUTY = "Náměstek"
    ASSISTANT = "Asistentka"


class Task(db.Model):
    __tablename__ = "tasks"
    # Bez AUTOINCREMENT by SQLite po smazání posledního úkolu použil jeho číslo znovu
    __table_args__ = {"sqlite_autoincrement": True}

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # V UI jako ÚKOL-{id}
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    task_type = db.Column(db.Enum(TaskType), default=TaskType.STANDARD, nullable=False)
    assignee_target = db.Column(db.String(255), nullable=True)  # Komu slíbeno / cílová osoba
    creator = db.Column(db.Enum(UserRole), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    priority = db.Column(db.Enum(Priority), default=Priority.MEDIUM, nullable=False)
    status = db.Column(db.Enum(TaskStatus), default=TaskStatus.OPEN, nullable=False)
    due_date = db.Column(db.DateTime, nullable=True)  # Lokální čas (APP_TIMEZONE), bez tzinfo

    # Synchronizace s Outlookem
    sync_deputy_cal = db.Column(db.Boolean, default=False, nullable=False)
    sync_assistant_cal = db.Column(db.Boolean, default=False, nullable=False)
    outlook_event_id_deputy = db.Column(db.String(255), nullable=True)
    outlook_event_id_assistant = db.Column(db.String(255), nullable=True)

    # Kdy bylo odesláno upozornění na blížící se termín (aby se neposílalo opakovaně)
    deadline_notified_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def code(self) -> str:
        return f"ÚKOL-{self.id}"

    @property
    def is_commitment(self) -> bool:
        return self.task_type == TaskType.COMMITMENT

    def __repr__(self) -> str:
        return f"<Task {self.code} {self.title!r}>"


class TaskHistory(db.Model):
    __tablename__ = "task_history"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # SET NULL místo CASCADE, aby záznam „Smazáno“ zůstal v auditu i po smazání úkolu
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    task_code = db.Column(db.String(32), nullable=False)
    task_title = db.Column(db.String(255), nullable=True)
    user = db.Column(db.Enum(UserRole), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # "Vytvořeno", "Změna stavu", "Smazáno", ...
    changes_summary = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utcnow, nullable=False)
