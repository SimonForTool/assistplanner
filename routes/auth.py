"""Přihlášení a volba profilu (náměstek / asistentka, jména z config)."""
import hmac
import re
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import config
from models import UserRole

bp = Blueprint("auth", __name__)

PASSWORDS = {UserRole.DEPUTY: config.DEPUTY_PASSWORD, UserRole.ASSISTANT: config.ASSISTANT_PASSWORD}
MIN_PASSWORD_LENGTH = 8


# --- Hesla: změněné heslo (otisk v databázi) má přednost před heslem z .env ---

def _password_hash(role: UserRole) -> str:
    from services.task_service import get_setting
    return get_setting(f"{role.name}_password_hash")


def has_password(role: UserRole) -> bool:
    return bool(_password_hash(role) or PASSWORDS.get(role))


def check_password(role: UserRole, password: str) -> bool:
    stored = _password_hash(role)
    if stored:
        return check_password_hash(stored, password)
    expected = PASSWORDS.get(role)
    return not expected or hmac.compare_digest(password.encode(), expected.encode())


def set_password(role: UserRole, password: str) -> None:
    from services.task_service import set_setting
    set_setting(f"{role.name}_password_hash", generate_password_hash(password))


def _password_version(role: UserRole) -> str:
    """Otisk aktuálního hesla – po změně hesla se ostatní přihlášená zařízení odhlásí."""
    stored = _password_hash(role)
    return stored[-16:] if stored else "env"


def current_role() -> UserRole | None:
    role = session.get("role")
    return UserRole[role] if role in UserRole.__members__ else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        role = current_role()
        if role is None:
            return redirect(url_for("auth.login", next=request.full_path))
        if session.get("pwv") != _password_version(role):
            # heslo se mezitím změnilo (na jiném zařízení) – je potřeba se přihlásit znovu
            session.clear()
            flash("Heslo bylo změněno – přihlaste se prosím znovu.", "info")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapped


def safe_next(target: str | None, fallback: str | None = None) -> str:
    # Jen relativní cesty v rámci aplikace (ochrana proti open redirect)
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return fallback or url_for("dashboard.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = UserRole.__members__.get(request.form.get("role", ""))
        password = request.form.get("password", "")
        if role and check_password(role, password):
            csrf = session.get("_csrf")
            session.clear()
            session["role"] = role.name
            session["pwv"] = _password_version(role)
            session["_csrf"] = csrf
            session.permanent = True
            return redirect(safe_next(request.args.get("next")))
        flash("Nesprávné heslo.", "danger")
    return render_template("login.html", passwordless=not all(has_password(r) for r in UserRole))


@bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    role = current_role()
    current = request.form.get("current", "")
    new = request.form.get("new", "")
    confirm = request.form.get("confirm", "")
    if has_password(role) and not check_password(role, current):
        flash("Současné heslo není správné.", "danger")
    elif len(new) < MIN_PASSWORD_LENGTH:
        flash(f"Nové heslo musí mít alespoň {MIN_PASSWORD_LENGTH} znaků.", "danger")
    elif new != confirm:
        flash("Nová hesla se neshodují.", "danger")
    elif new == current:
        flash("Nové heslo je stejné jako současné.", "warning")
    else:
        set_password(role, new)
        session["pwv"] = _password_version(role)  # toto zařízení zůstane přihlášené
        flash("Heslo bylo změněno. Ostatní zařízení s tímto profilem se odhlásí.", "success")
    return redirect(url_for("auth.profile") + "#password")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """Moje kontakty pro upozornění (e-mail, telefon) – každý profil si je spravuje sám."""
    from services import task_service

    role = current_role()
    if request.method == "POST":
        from services.notify_service import normalize_phone

        email = request.form.get("email", "").strip()
        phone = normalize_phone(request.form.get("phone", "").strip())
        if email and "@" not in email:
            flash("Zadejte platný e-mail.", "danger")
        elif phone and not re.fullmatch(r"\+\d{8,15}", phone):
            flash("Telefon zadejte ve tvaru +420 123 456 789.", "danger")
        else:
            task_service.set_contacts(role, email, phone)
            flash("Kontakty byly uloženy.", "success")
            return redirect(url_for("auth.profile"))
    from services import gcal_service

    return render_template("profile.html",
                           email=task_service.get_contact(role, "email"),
                           phone=task_service.get_contact(role, "phone"),
                           gcal_secret=gcal_service.ensure_secret(),
                           gcal_url=gcal_service.script_url())


@bp.route("/profile/test", methods=["POST"])
@login_required
def profile_test():
    """Pošle zkušební e-mail a SMS na uložené kontakty a ukáže výsledek."""
    from services import notify_service, task_service

    role = current_role()
    results = notify_service.send_test(task_service.get_contact(role, "email"),
                                       task_service.get_contact(role, "phone"))
    for kind, result in results.items():
        flash(f"{kind[0].upper() + kind[1:]}: {result}", "success" if result == "odesláno" else
              "info" if result.startswith(("není", "na serveru")) else "danger")
    return redirect(url_for("auth.profile"))


@bp.route("/profile/gcal", methods=["POST"])
@login_required
def profile_gcal():
    """Propojení s Google kalendářem: uložení adresy skriptu, nový klíč, test, hromadný zápis."""
    from services import gcal_service, task_service

    action = request.form.get("action", "test")
    try:
        if action in ("new_secret", "save_url"):
            task_service.set_setting("gcal_calendar", "")  # „Propojeno“ až po úspěšném testu
        if action == "new_secret":
            gcal_service.ensure_secret(regenerate=True)
            flash("Vytvořen nový tajný klíč – vložte nový řádek const SECRET do skriptu a nasaďte novou verzi.",
                  "warning")
            return redirect(url_for("auth.profile") + "#gcal")
        if action == "save_url":
            gcal_service.save_url(request.form.get("url", ""))
        name = gcal_service.ping()
        if action == "sync_all":
            count, errors = task_service.sync_all_to_gcal()
            for e in errors:
                flash(e, "danger")
            flash(f"Do Google kalendáře zapsáno úkolů: {count}.", "success")
        else:
            flash(f"✅ Google kalendář je propojen: {name}.", "success")
    except gcal_service.GCalError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("auth.profile") + "#gcal")
    if request.form.get("sync_all"):
        count, errors = task_service.sync_all_to_gcal()
        for e in errors:
            flash(e, "danger")
        flash(f"Do Google kalendáře „{name}“ zapsáno úkolů: {count}.", "success")
    else:
        flash(f"Google kalendář je připojen: „{name}“.", "success")
    return redirect(url_for("auth.profile"))
