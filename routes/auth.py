"""Přihlášení a volba role (Náměstek / Asistentka)."""
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
