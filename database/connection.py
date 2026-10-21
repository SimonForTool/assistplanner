"""SQLAlchemy engine, session a inicializace databáze."""
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

import config
from database.models import Base, Priority, Task, TaskHistory, TaskStatus, TaskType, UserRole

_is_sqlite = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(seed: bool | None = None) -> None:
    Base.metadata.create_all(engine)
    if seed if seed is not None else config.SEED_DEMO_DATA:
        seed_demo_data()


def seed_demo_data() -> None:
    """Naplní prázdnou databázi několika ukázkovými úkoly."""
    with get_session() as s:
        if s.scalar(select(Task.id).limit(1)) is not None:
            return
        today = datetime.now(config.TIMEZONE).replace(tzinfo=None, second=0, microsecond=0)
        demo = [
            Task(title="Porada vedení odboru", task_type=TaskType.STANDARD,
                 creator=UserRole.ASSISTANT, location="Zasedačka 3.12",
                 priority=Priority.HIGH, due_date=today.replace(hour=10, minute=0)),
            Task(title="Poslat stanovisko k rozpočtu", task_type=TaskType.COMMITMENT,
                 assignee_target="Ing. Novák (MF)", creator=UserRole.DEPUTY,
                 priority=Priority.URGENT, due_date=today + timedelta(hours=20)),
            Task(title="Telefonát s hejtmanem", task_type=TaskType.STANDARD,
                 assignee_target="Hejtman kraje", creator=UserRole.ASSISTANT,
                 priority=Priority.MEDIUM, due_date=today.replace(hour=14, minute=30)),
            Task(title="Podklady pro výbor", task_type=TaskType.STANDARD,
                 creator=UserRole.DEPUTY, priority=Priority.LOW,
                 status=TaskStatus.IN_PROGRESS, due_date=today + timedelta(days=3),
                 created_at=today - timedelta(days=10)),
            Task(title="Ozvat se ohledně dotačního programu", task_type=TaskType.COMMITMENT,
                 assignee_target="Starostka Mgr. Dvořáková", creator=UserRole.DEPUTY,
                 priority=Priority.MEDIUM, due_date=today - timedelta(days=1),
                 created_at=today - timedelta(days=9)),
        ]
        s.add_all(demo)
        s.flush()
        for t in demo:
            s.add(TaskHistory(task_id=t.id, task_code=t.code, task_title=t.title,
                              user=t.creator, action="Vytvořeno",
                              changes_summary="Ukázková data"))


if __name__ == "__main__":
    init_db(seed=True)
    print(f"Databáze inicializována: {config.DATABASE_URL}")
