"""Záložka „Co komu slíbil" – pouze závazky."""
import pandas as pd
import streamlit as st

from database.models import TaskType
from services import task_service
from ui.dashboard import export_buttons, is_overdue, render_task_detail, selectable_table
from utils.helpers import ACTIVE_STATUSES, fmt_dt, now_local, status_label


def render() -> None:
    st.header("🤝 Co komu slíbil")
    commitments = [t for t in task_service.list_tasks() if t.task_type == TaskType.COMMITMENT]

    c1, c2 = st.columns([3, 1])
    search = c1.text_input("🔎 Hledat osobu nebo závazek")
    only_active = c2.toggle("Jen nesplněné", value=True)
    s = search.strip().lower()
    rows = [
        t for t in commitments
        if (not only_active or t.status in ACTIVE_STATUSES)
        and (not s or s in f"{t.title} {t.assignee_target or ''} {t.location or ''}".lower())
    ]

    overdue = [t for t in rows if is_overdue(t)]
    m1, m2 = st.columns(2)
    m1.metric("Nesplněné závazky", sum(1 for t in commitments if t.status in ACTIVE_STATUSES))
    m2.metric("Po termínu", len(overdue))
    if overdue:
        st.error("Po termínu: " + "; ".join(f"**{t.assignee_target or '?'}** – {t.title}"
                                            for t in overdue))

    if not rows:
        st.info("Žádné závazky.")
        return
    df = pd.DataFrame([{
        "Komu slíbeno": t.assignee_target or "—",
        "Co": ("⚠️ " if is_overdue(t) else "") + t.title,
        "Kde": t.location or "",
        "Termín": fmt_dt(t.due_date),
        "Zadal(a)": t.creator.value,
        "Stav": status_label(t.status),
        "ID": t.code,
    } for t in rows])
    selected = selectable_table(df, rows, "commitments_table")
    export_buttons(df, f"zavazky_{now_local():%Y%m%d}")
    if selected:
        render_task_detail(selected)
