"""Assistant Planner – vstupní bod Streamlit aplikace.

Spuštění:  streamlit run app.py
"""
import hmac
import logging

import streamlit as st

import config
from database.connection import init_db
from database.models import UserRole
from services import task_service
from ui import commitments, dashboard, history, task_form
from utils.helpers import current_user, show_flashes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

st.set_page_config(page_title="Assistant Planner", page_icon="🗂️", layout="wide")

st.markdown("""
<style>
  div[data-testid="stMetric"] {background:#f5f8fc;border-radius:10px;padding:10px 14px;}
  div[data-testid="stHorizontalBlock"] button {min-height:3rem;}
  @media (max-width: 640px) { h1, h2 {font-size:1.4rem !important;} }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def _init() -> bool:
    init_db()
    return True


@st.cache_data(ttl=600, show_spinner=False)
def _deadline_check() -> int:
    """Kontrola blížících se závazků nejvýše jednou za 10 minut (deduplikace je i v DB)."""
    try:
        return task_service.check_deadline_notifications()
    except Exception as exc:
        logging.getLogger(__name__).warning("Kontrola termínů selhala: %s", exc)
        return 0


PASSWORDS = {UserRole.DEPUTY: config.DEPUTY_PASSWORD, UserRole.ASSISTANT: config.ASSISTANT_PASSWORD}
PAGES = {
    "📋 Přehled": dashboard.render,
    "➕ Nový úkol": task_form.render,
    "🤝 Co komu slíbil": commitments.render,
    "🕓 Historie změn": history.render,
}


def login() -> None:
    st.title("🗂️ Assistant Planner")
    with st.form("login"):
        role = st.radio("Přihlásit jako", list(UserRole), format_func=lambda r: r.value, horizontal=True)
        password = st.text_input("Heslo", type="password")
        if st.form_submit_button("Přihlásit", type="primary"):
            expected = PASSWORDS[role]
            if not expected or hmac.compare_digest(password.encode(), expected.encode()):
                st.session_state["user_role"] = role
                st.rerun()
            st.error("Nesprávné heslo.")
    if not all(PASSWORDS.values()):
        st.caption("⚠️ Některá role nemá nastavené heslo v `.env` – přihlášení bez hesla.")


def sidebar() -> str:
    user = current_user()
    with st.sidebar:
        st.markdown(f"### 🗂️ Assistant Planner\nPřihlášen(a): **{user.value}**")
        page = st.radio("Navigace", list(PAGES), label_visibility="collapsed")
        st.divider()
        st.caption("Integrace")
        st.caption(("🟢" if config.openai_enabled() else "⚪") + " OpenAI (hlas, AI)")
        st.caption(("🟢" if config.graph_enabled() else "⚪") + " Outlook kalendář"
                   + ("" if config.graph_enabled() else " – mock"))
        notif = config.TELEGRAM_BOT_TOKEN or config.NOTIFY_WEBHOOK_URL or config.SMTP_HOST
        st.caption(("🟢" if notif else "⚪") + " Notifikace" + ("" if notif else " – jen log"))
        st.divider()
        if st.button("Odhlásit", width="stretch"):
            st.session_state.clear()
            st.rerun()
    return page


def main() -> None:
    _init()
    if current_user() is None:
        login()
        return
    _deadline_check()
    page = sidebar()
    show_flashes()
    PAGES[page]()


main()
