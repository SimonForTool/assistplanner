"""SQLAlchemy modely: úkoly a jejich auditní historie."""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


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


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)  # V UI jako ÚKOL-{id}
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(Enum(TaskType), default=TaskType.STANDARD, nullable=False)
    assignee_target = Column(String(255), nullable=True)  # Komu slíbeno / cílová osoba
    creator = Column(Enum(UserRole), nullable=False)
    location = Column(String(255), nullable=True)
    priority = Column(Enum(Priority), default=Priority.MEDIUM, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.OPEN, nullable=False)
    due_date = Column(DateTime, nullable=True)  # Lokální čas (APP_TIMEZONE), bez tzinfo

    # Synchronizace s Outlookem
    sync_deputy_cal = Column(Boolean, default=False, nullable=False)
    sync_assistant_cal = Column(Boolean, default=False, nullable=False)
    outlook_event_id_deputy = Column(String(255), nullable=True)
    outlook_event_id_assistant = Column(String(255), nullable=True)

    # Kdy byla odeslána upozornění (aby se neposílala opakovaně)
    deadline_notified_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    history = relationship(
        "TaskHistory",
        back_populates="task",
        passive_deletes=True,
        order_by="TaskHistory.timestamp.desc()",
    )

    @property
    def code(self) -> str:
        return f"ÚKOL-{self.id}"

    def __repr__(self) -> str:
        return f"<Task {self.code} {self.title!r}>"


class TaskHistory(Base):
    __tablename__ = "task_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # SET NULL místo CASCADE, aby záznam o smazání zůstal v auditu i po smazání úkolu
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    task_code = Column(String(32), nullable=False)
    task_title = Column(String(255), nullable=True)
    user = Column(Enum(UserRole), nullable=False)
    action = Column(String(50), nullable=False)  # "Vytvořeno", "Změna stavu", "Smazáno", ...
    changes_summary = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utcnow, nullable=False)

    task = relationship("Task", back_populates="history")
