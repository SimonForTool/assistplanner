"""Přihlášení a volba profilu (náměstek / asistentka, jména z config)."""
import hmac
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
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        if email and "@" not in email:
            flash("Zadejte platný e-mail.", "danger")
        elif phone and not phone.replace(" ", "").lstrip("+").isdigit():
            flash("Telefon zadejte ve tvaru +420 123 456 789.", "danger")
        else:
            task_service.set_contacts(role, email, phone.replace(" ", ""))
            flash("Kontakty byly uloženy.", "success")
            return redirect(url_for("auth.profile"))
    return render_template("profile.html",
                           email=task_service.get_contact(role, "email"),
                           phone=task_service.get_contact(role, "phone"))
