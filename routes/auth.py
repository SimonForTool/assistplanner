"""Přihlášení a volba profilu (náměstek / asistentka, jména z config)."""
import hmac
import re
from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

import config
from models import UserRole

bp = Blueprint("auth", __name__)

PASSWORDS = {UserRole.DEPUTY: config.DEPUTY_PASSWORD, UserRole.ASSISTANT: config.ASSISTANT_PASSWORD}


def current_role() -> UserRole | None:
    role = session.get("role")
    return UserRole[role] if role in UserRole.__members__ else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_role() is None:
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
        expected = PASSWORDS.get(role) if role else None
        if role and (not expected or hmac.compare_digest(password.encode(), expected.encode())):
            csrf = session.get("_csrf")
            session.clear()
            session["role"] = role.name
            session["_csrf"] = csrf
            session.permanent = True
            return redirect(safe_next(request.args.get("next")))
        flash("Nesprávné heslo.", "danger")
    return render_template("login.html", passwordless=not all(PASSWORDS.values()))


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
    return render_template("profile.html",
                           email=task_service.get_contact(role, "email"),
                           phone=task_service.get_contact(role, "phone"))


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
    """Test spojení s Google kalendářem, případně zápis všech budoucích pracovních úkolů."""
    from services import gcal_service, task_service

    try:
        name = gcal_service.ping()
    except gcal_service.GCalError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("auth.profile"))
    if request.form.get("sync_all"):
        count, errors = task_service.sync_all_to_gcal()
        for e in errors:
            flash(e, "danger")
        flash(f"Do Google kalendáře „{name}“ zapsáno úkolů: {count}.", "success")
    else:
        flash(f"Google kalendář je připojen: „{name}“.", "success")
    return redirect(url_for("auth.profile"))
