"""Prohlížeč auditní stopy."""
import pandas as pd
import streamlit as st

from database.models import UserRole
from services import task_service
from utils.helpers import fmt_dt, utc_to_local


def _to_df(entries) -> pd.DataFrame:
    return pd.DataFrame([{
        "Čas": fmt_dt(utc_to_local(h.timestamp)),
        "Úkol": h.task_code,
        "Název": h.task_title or "",
        "Uživatel": h.user.value,
        "Akce": h.action,
        "Změny": h.changes_summary or "",
    } for h in entries])


def render_task_history(task_id: int) -> None:
    entries = task_service.get_history(task_id)
    if not entries:
        st.caption("Žádné záznamy.")
        return
    st.dataframe(_to_df(entries).drop(columns=["Úkol", "Název"]),
                 hide_index=True, width="stretch")


def render() -> None:
    st.header("🕓 Historie změn")
    entries = task_service.get_history(limit=2000)
    if not entries:
        st.info("Zatím žádné záznamy.")
        return
    df = _to_df(entries)

    c1, c2, c3 = st.columns([2, 1, 1])
    search = c1.text_input("Hledat (kód, název, změny)", placeholder="např. ÚKOL-12")
    users = c2.multiselect("Uživatel", [u.value for u in UserRole])
    actions = c3.multiselect("Akce", sorted(df["Akce"].unique()))

    if search:
        mask = (df["Úkol"].str.contains(search, case=False, regex=False)
                | df["Název"].str.contains(search, case=False, regex=False)
                | df["Změny"].str.contains(search, case=False, regex=False))
        df = df[mask]
    if users:
        df = df[df["Uživatel"].isin(users)]
    if actions:
        df = df[df["Akce"].isin(actions)]

    st.caption(f"{len(df)} záznamů")
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Změny": st.column_config.TextColumn(width="large")})
    st.download_button("⬇️ Export CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       "historie_zmen.csv", "text/csv")
