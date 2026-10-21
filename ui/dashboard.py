"""Hlavní přehled: KPI, ranní AI briefing a interaktivní tabulka úkolů."""
from datetime import timedelta
from io import BytesIO

import pandas as pd
import streamlit as st

import config
from database.models import Priority, Task, TaskStatus, TaskType, UserRole, utcnow
from services import ai_service, task_service
from services.outlook_service import get_outlook
from ui import history, task_form
from utils.helpers import (
    ACTIVE_STATUSES,
    current_user,
    flash,
    fmt_dt,
    now_local,
    priority_badge,
    priority_label,
    status_badge,
    status_label,
    today_bounds,
)


# --- Sdílené komponenty (používá i ui/commitments.py) ---

def is_aging(t: Task) -> bool:
    return t.status in ACTIVE_STATUSES and t.created_at < utcnow() - timedelta(days=config.AGING_DAYS)


def is_overdue(t: Task) -> bool:
    return t.status in ACTIVE_STATUSES and t.due_date is not None and t.due_date < now_local()


def export_buttons(df: pd.DataFrame, basename: str) -> None:
    c1, c2, _ = st.columns([1, 1, 4])
    c1.download_button("⬇️ CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       f"{basename}.csv", "text/csv", width="stretch")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Úkoly")
    c2.download_button("⬇️ Excel", buf.getvalue(), f"{basename}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")


def selectable_table(df: pd.DataFrame, tasks: list[Task], key: str) -> Task | None:
    """Tabulka s výběrem řádku; vrací vybraný úkol."""
    event = st.dataframe(
        df, hide_index=True, width="stretch", key=key,
        on_select="rerun", selection_mode="single-row",
        column_config={"Název": st.column_config.TextColumn(width="large"),
                       "Co": st.column_config.TextColumn(width="large")},
    )
    rows = event.selection.rows if event and event.selection else []
    return tasks[rows[0]] if rows else None


def render_task_detail(task: Task) -> None:
    """Detail vybraného úkolu s rychlými akcemi, úpravou a historií."""
    user = current_user()
    with st.container(border=True):
        st.markdown(
            f"### {task.code} · {task.title}\n"
            f"{priority_badge(task.priority)} {status_badge(task.status)} "
            f"&nbsp; 🗓️ {fmt_dt(task.due_date)}"
            + (f" &nbsp; 📍 {task.location}" if task.location else "")
            + (f" &nbsp; 👤 {task.assignee_target}" if task.assignee_target else "")
            + f" &nbsp; ✍️ zadal(a): {task.creator.value}",
            unsafe_allow_html=True,
        )
        cal = [r.value for r, flag in ((UserRole.DEPUTY, task.outlook_event_id_deputy),
                                       (UserRole.ASSISTANT, task.outlook_event_id_assistant)) if flag]
        if cal:
            st.caption("📆 V kalendáři: " + ", ".join(cal))

        actions = [
            ("⏳ Probíhá", TaskStatus.IN_PROGRESS),
            ("✅ Uzavřít", TaskStatus.CLOSED),
            ("🚫 Zrušit", TaskStatus.CANCELLED),
            ("🔄 Znovu otevřít", TaskStatus.OPEN),
        ]
        cols = st.columns(len(actions) + 1)
        for col, (label, status) in zip(cols, actions):
            if col.button(label, key=f"st_{task.id}_{status.name}", width="stretch",
                          disabled=task.status == status):
                _, warnings = task_service.set_status(task.id, status, user)
                for w in warnings:
                    flash(w, "warning")
                flash(f"{task.code}: stav změněn na „{status.value}“.")
                st.rerun()
        confirm_key = f"confirm_del_{task.id}"
        if cols[-1].button("🗑️ Smazat", key=f"del_{task.id}", width="stretch"):
            st.session_state[confirm_key] = True
        if st.session_state.get(confirm_key):
            st.warning(f"Opravdu smazat {task.code}? Smažou se i události v Outlooku.")
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("Ano, smazat", type="primary", key=f"del_yes_{task.id}"):
                for w in task_service.delete_task(task.id, user):
                    flash(w, "warning")
                st.session_state.pop(confirm_key, None)
                flash(f"Úkol {task.code} byl smazán.")
                st.rerun()
            if c2.button("Ne", key=f"del_no_{task.id}"):
                st.session_state.pop(confirm_key, None)
                st.rerun()

        tab_edit, tab_hist = st.tabs(["✏️ Upravit", "🕓 Historie"])
        with tab_edit:
            if task.description:
                st.markdown(f"**Popis:** {task.description}")
            task_form.render_edit(task)
        with tab_hist:
            history.render_task_history(task.id)


# --- Přehled ---

def _kpis(tasks: list[Task]) -> None:
    start, end = today_bounds()
    active = [t for t in tasks if t.status in ACTIVE_STATUSES]
    due_today = sum(1 for t in active if t.due_date and start <= t.due_date < end)
    overdue = sum(1 for t in active if is_overdue(t))
    aging = sum(1 for t in active if is_aging(t))
    hot = sum(1 for t in active if t.priority in (Priority.HIGH, Priority.URGENT))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("📅 Dnes k termínu", due_today)
    c2.metric("⚠️ Po termínu", overdue)
    c3.metric(f"🐢 Otevřeno > {config.AGING_DAYS} dní", aging)
    c4.metric("🔥 Vysoká / urgentní", hot)


def _briefing(tasks: list[Task]) -> None:
    key = f"briefing_{now_local().date().isoformat()}"
    with st.container(border=True):
        c1, c2 = st.columns([5, 1])
        c1.markdown("#### ☀️ Ranní briefing")
        regenerate = c2.button("🔄 Generovat", width="stretch")
        if regenerate or key not in st.session_state:
            active = [t for t in tasks if t.status in ACTIVE_STATUSES]
            calendar = []
            try:
                calendar = get_outlook().list_events_today(UserRole.DEPUTY)
            except Exception as exc:
                st.caption(f"Kalendář nedostupný: {exc}")
            with st.spinner("Připravuji briefing…"):
                st.session_state[key] = ai_service.generate_morning_briefing(active, calendar)
        text, ai_used = st.session_state[key]
        st.markdown(text)
        if not ai_used:
            st.caption("Sestaveno bez AI (chybí OPENAI_API_KEY nebo AI neodpověděla).")


def _filters(tasks: list[Task]) -> list[Task]:
    c1, c2, c3, c4 = st.columns([2, 1.3, 1.3, 1])
    search = c1.text_input("🔎 Hledat", placeholder="název, osoba, místo, ÚKOL-…")
    statuses = c2.multiselect("Stav", list(TaskStatus), default=list(ACTIVE_STATUSES),
                              format_func=status_label)
    priorities = c3.multiselect("Priorita", list(Priority), format_func=priority_label)
    creators = c4.multiselect("Zadal(a)", list(UserRole), format_func=lambda r: r.value)
    s = search.strip().lower()
    return [
        t for t in tasks
        if (not statuses or t.status in statuses)
        and (not priorities or t.priority in priorities)
        and (not creators or t.creator in creators)
        and (not s or s in " ".join(filter(None, [t.code, t.title, t.description,
                                                   t.assignee_target, t.location])).lower())
    ]


def _tasks_df(tasks: list[Task]) -> pd.DataFrame:
    return pd.DataFrame([{
        "ID": t.code,
        "Název": ("⚠️ " if is_overdue(t) else "") + t.title,
        "Typ": "🤝 Závazek" if t.task_type == TaskType.COMMITMENT else "Úkol",
        "Zadal(a)": t.creator.value,
        "Priorita": priority_label(t.priority),
        "Stav": status_label(t.status),
        "Termín": fmt_dt(t.due_date),
        "Místo": t.location or "",
        "Komu / pro koho": t.assignee_target or "",
    } for t in tasks], columns=["ID", "Název", "Typ", "Zadal(a)", "Priorita", "Stav",
                                "Termín", "Místo", "Komu / pro koho"])


def render() -> None:
    st.header(f"📋 Přehled · {now_local():%d.%m.%Y}")
    tasks = task_service.list_tasks()
    _kpis(tasks)
    _briefing(tasks)

    st.subheader("Úkoly")
    filtered = _filters(tasks)
    if not filtered:
        st.info("Žádné úkoly neodpovídají filtru.")
        return
    df = _tasks_df(filtered)
    st.caption(f"{len(filtered)} úkolů · klikněte na řádek pro detail a akce")
    selected = selectable_table(df, filtered, "dashboard_table")
    export_buttons(df, f"ukoly_{now_local():%Y%m%d}")
    if selected:
        render_task_detail(selected)
