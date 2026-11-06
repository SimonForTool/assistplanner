"""Flask application factory pro Syncho – Assistant Planner.

Lokální spuštění:   python app.py          (http://localhost:5000)
PythonAnywhere:     viz wsgi.py a README.md
"""
import logging
import mimetypes

import click
import secrets
import time

from flask import Flask, abort, request, session
from sqlalchemy import event
from sqlalchemy.engine import Engine

import config
from models import Priority, TaskStatus, TaskType, UserRole, db
from services import task_service
from utils import helpers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)
mimetypes.add_type("application/manifest+json", ".webmanifest")

DEADLINE_CHECK_INTERVAL = 600  # s
_last_deadline_check = 0.0


@event.listens_for(Engine, "connect")
def _sqlite_foreign_keys(dbapi_conn, _):
    # SQLite bez tohoto ignoruje ON DELETE SET NULL v historii
    if type(dbapi_conn).__module__.startswith("sqlite3"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        SQLALCHEMY_DATABASE_URI=config.DATABASE_URL,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        MAX_CONTENT_LENGTH=config.MAX_UPLOAD_MB * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    db.init_app(app)

    from routes import auth, calendar, commitments, dashboard, history, tasks
    for bp in (auth.bp, dashboard.bp, tasks.bp, calendar.bp, commitments.bp, history.bp):
        app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        task_service.ensure_schema()
        if config.SEED_DEMO_DATA:
            task_service.seed_demo_data()
        task_service.apply_commitment_rule_to_existing()

    @app.before_request
    def _csrf_protect():
        if request.method == "POST":
            sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf", "")):
                abort(400, "Neplatný bezpečnostní token formuláře – obnovte stránku.")

    @app.before_request
    def _deadline_check():
        # PythonAnywhere nemá trvale běžící proces; kontrolu spouštíme při provozu
        # (nejvýše jednou za 10 minut) a navíc ji lze plánovat příkazem `flask check-deadlines`.
        global _last_deadline_check
        if session.get("role") and time.monotonic() - _last_deadline_check > DEADLINE_CHECK_INTERVAL:
            _last_deadline_check = time.monotonic()
            try:
                task_service.check_deadline_notifications()
            except Exception as exc:
                log.warning("Kontrola termínů selhala: %s", exc)

    def _gcal_name():
        from services import gcal_service
        return gcal_service.calendar_name()

    @app.context_processor
    def _template_globals():
        return {
            "csrf_token": csrf_token,
            "current_role": auth.current_role(),
            "Priority": Priority,
            "TaskStatus": TaskStatus,
            "TaskType": TaskType,
            "UserRole": UserRole,
            "PRIORITY_BADGES": helpers.PRIORITY_BADGES,
            "STATUS_BADGES": helpers.STATUS_BADGES,
            "is_overdue": task_service.is_overdue,
            "known_delegates": task_service.known_delegates,
            "contact": task_service.get_contact,
            "email_recipients": task_service.email_recipients,
            "gcal_name": _gcal_name,
            "settings": config,
        }

    app.jinja_env.filters["dt"] = helpers.fmt_dt
    app.jinja_env.filters["local"] = helpers.utc_to_local

    @app.cli.command("check-deadlines")
    def _check_deadlines_cmd():
        """Pošle upozornění na závazky s termínem do 24 h (pro plánovanou úlohu)."""
        print(f"Odesláno upozornění: {task_service.check_deadline_notifications()}")

    @app.cli.command("test-notify")
    @click.option("--email", default="", help="Adresa pro zkušební e-mail")
    @click.option("--phone", default="", help="Telefon pro zkušební SMS (+420…)")
    def _test_notify_cmd(email, phone):
        """Ověří nastavení SMTP / Twilio odesláním zkušební zprávy."""
        from services import notify_service
        for kind, result in notify_service.send_test(email or None, phone or None).items():
            print(f"{kind}: {result}")

    @app.cli.command("gcal-sync")
    def _gcal_sync_cmd():
        """Otestuje Google kalendář a zapíše do něj budoucí pracovní úkoly."""
        from services import gcal_service
        print("Kalendář:", gcal_service.ping())
        count, errors = task_service.sync_all_to_gcal()
        print(f"Zapsáno: {count}", *errors, sep="\n")

    @app.cli.command("seed")
    def _seed_cmd():
        """Naplní prázdnou databázi ukázkovými daty."""
        print("Hotovo." if task_service.seed_demo_data() else "Databáze není prázdná.")

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
