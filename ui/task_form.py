"""Zadávání a úprava úkolů: šablony, hlasový vstup s AI a ruční formulář."""
from datetime import time, timedelta

import streamlit as st

import config
from database.models import Priority, Task, TaskStatus, TaskType
from services import ai_service, task_service
from utils.helpers import (
    combine_date_time,
    current_user,
    flash,
    now_local,
    parse_dt,
    priority_label,
    status_label,
)

PREFILL_KEY = "new_task_prefill"
VERSION_KEY = "new_task_form_version"


def _template(title: str, priority: Priority, days: int, hour: int, deputy_cal: bool) -> dict:
    due = (now_local() + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return {"title": title, "task_type": TaskType.STANDARD, "priority": priority,
            "due_date": due, "sync_deputy_cal": deputy_cal}


TEMPLATES = {
    "📅 Schůzka": lambda: _template("Schůzka: ", Priority.MEDIUM, 1, 10, True),
    "📞 Telefonát": lambda: _template("Telefonát: ", Priority.MEDIUM, 0, 14, False),
    "📄 Příprava podkladů": lambda: _template("Příprava podkladů: ", Priority.HIGH, 3, 9, False),
    "✍️ Schválení": lambda: _template("Schválení: ", Priority.HIGH, 2, 9, False),
}


def _set_prefill(data: dict) -> None:
    st.session_state[PREFILL_KEY] = data
    st.session_state[VERSION_KEY] = st.session_state.get(VERSION_KEY, 0) + 1


def ai_result_to_prefill(result: dict, transcript: str) -> dict:
    return {
        "title": result.get("title") or transcript[:80],
        "description": transcript,
        "task_type": next((t for t in TaskType if t.value == result.get("task_type")), TaskType.STANDARD),
        "assignee_target": result.get("assignee_target") or "",
        "location": result.get("location") or "",
        "priority": next((p for p in Priority if p.value == result.get("priority")), Priority.MEDIUM),
        "due_date": parse_dt(result.get("due_date")),
    }


def task_fields(key: str, values: dict, show_status: bool = False) -> dict:
    """Vykreslí pole úkolu (uvnitř st.form) a vrátí slovník hodnot pro task_service."""
    title = st.text_input("Název *", value=values.get("title", ""), key=f"{key}_title")
    c1, c2 = st.columns(2)
    types = list(TaskType)
    task_type = c1.selectbox("Typ", types, index=types.index(values.get("task_type", TaskType.STANDARD)),
                             format_func=lambda t: t.value, key=f"{key}_type")
    priorities = list(Priority)
    priority = c2.selectbox("Priorita", priorities,
                            index=priorities.index(values.get("priority", Priority.MEDIUM)),
                            format_func=priority_label, key=f"{key}_priority")
    c3, c4 = st.columns(2)
    assignee = c3.text_input("Komu slíbeno / pro koho", value=values.get("assignee_target") or "",
                             key=f"{key}_assignee")
    location = c4.text_input("Místo", value=values.get("location") or "", key=f"{key}_location")
    due = values.get("due_date")
    c5, c6, c7 = st.columns([2, 2, 1])
    due_d = c5.date_input("Termín – datum", value=due.date() if due else None,
                          format="DD.MM.YYYY", key=f"{key}_due_d")
    due_t = c6.time_input("Termín – čas", value=due.time() if due else time(9, 0),
                          step=timedelta(minutes=15), key=f"{key}_due_t")
    status = values.get("status", TaskStatus.OPEN)
    if show_status:
        statuses = list(TaskStatus)
        status = c7.selectbox("Stav", statuses, index=statuses.index(status),
                              format_func=status_label, key=f"{key}_status")
    description = st.text_area("Popis / poznámka", value=values.get("description") or "",
                               height=90, key=f"{key}_desc")
    c8, c9 = st.columns(2)
    sync_deputy = c8.checkbox("Přidat do kalendáře náměstka",
                              value=bool(values.get("sync_deputy_cal")), key=f"{key}_cal_dep")
    sync_assistant = c9.checkbox("Přidat do kalendáře asistentky",
                                 value=bool(values.get("sync_assistant_cal")), key=f"{key}_cal_ast")
    return {
        "title": title.strip(),
        "task_type": task_type,
        "priority": priority,
        "assignee_target": assignee.strip() or None,
        "location": location.strip() or None,
        "due_date": combine_date_time(due_d, due_t),
        "status": status,
        "description": description.strip() or None,
        "sync_deputy_cal": sync_deputy,
        "sync_assistant_cal": sync_assistant,
    }


def _show_warnings(warnings: list[str]) -> None:
    for w in warnings:
        flash(w, "warning")


def _voice_input() -> None:
    st.markdown("##### 🎙️ Nadiktovat úkol")
    if not config.openai_enabled():
        st.info("Hlasové zadání vyžaduje `OPENAI_API_KEY` v souboru `.env`. "
                "Můžete ale vložit text níže – bez AI se použije jako název úkolu.")
    audio = st.audio_input("Nahrát hlasovou poznámku", key=f"audio_{st.session_state.get(VERSION_KEY, 0)}")
    text = st.text_area("…nebo napsat volným textem",
                        placeholder="Např.: Slíbil jsem panu Novákovi z MF, že mu do pátku "
                                    "pošlu stanovisko k rozpočtu.",
                        key=f"free_text_{st.session_state.get(VERSION_KEY, 0)}", height=80)
    if st.button("✨ Zpracovat", type="primary", disabled=not (audio or text.strip())):
        try:
            transcript = text.strip()
            if audio is not None:
                with st.spinner("Přepisuji nahrávku…"):
                    transcript = ai_service.transcribe_audio(audio.getvalue(), audio.name or "nahravka.wav")
            if config.openai_enabled():
                with st.spinner("Strukturuji zadání…"):
                    result = ai_service.extract_task(transcript)
                _set_prefill(ai_result_to_prefill(result, transcript))
                flash("Formulář byl předvyplněn – zkontrolujte jej a uložte.", "info")
            else:
                _set_prefill({"title": transcript[:80], "description": transcript})
            st.rerun()
        except ai_service.AIUnavailable as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Zpracování selhalo: {exc}")


def render() -> None:
    st.header("➕ Nový úkol")

    st.markdown("##### Rychlé šablony")
    cols = st.columns(len(TEMPLATES))
    for col, (label, factory) in zip(cols, TEMPLATES.items()):
        if col.button(label, width="stretch"):
            _set_prefill(factory())
            st.rerun()

    with st.expander("🎙️ Hlas / volný text s AI", expanded=PREFILL_KEY not in st.session_state):
        _voice_input()

    prefill = st.session_state.get(PREFILL_KEY, {})
    version = st.session_state.get(VERSION_KEY, 0)
    with st.form(f"new_task_{version}", clear_on_submit=False):
        st.markdown("##### Detail úkolu")
        data = task_fields(f"new{version}", prefill)
        c1, c2 = st.columns([1, 1])
        submitted = c1.form_submit_button("💾 Uložit úkol", type="primary", width="stretch")
        reset = c2.form_submit_button("Vyčistit", width="stretch")

    if reset:
        st.session_state.pop(PREFILL_KEY, None)
        st.session_state[VERSION_KEY] = version + 1
        st.rerun()
    if submitted:
        if not data["title"] or data["title"].endswith(":"):
            st.error("Vyplňte prosím název úkolu (doplňte text za šablonu).")
            return
        data.pop("status")
        task, warnings = task_service.create_task(data, current_user())
        _show_warnings(warnings)
        flash(f"Úkol {task.code} byl uložen.")
        st.session_state.pop(PREFILL_KEY, None)
        st.session_state[VERSION_KEY] = version + 1
        st.rerun()


def render_edit(task: Task) -> None:
    """Formulář pro úpravu existujícího úkolu (v detailu na přehledu)."""
    values = {f: getattr(task, f) for f in task_service.EDITABLE_FIELDS}
    # Klíč podle updated_at, aby se po rychlé akci (změna stavu) nepoužily staré hodnoty widgetů
    key = f"edit{task.id}_{task.updated_at.isoformat()}"
    with st.form(key):
        data = task_fields(key, values, show_status=True)
        submitted = st.form_submit_button("💾 Uložit změny", type="primary")
    if submitted:
        if not data["title"]:
            st.error("Název nesmí být prázdný.")
            return
        _, warnings = task_service.update_task(task.id, data, current_user())
        _show_warnings(warnings)
        flash(f"Úkol {task.code} byl upraven.")
        st.rerun()
