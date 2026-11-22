"""Logged-in user loading, role checks and CSRF protection."""
import functools
import secrets

from flask import abort, flash, g, redirect, request, session, url_for

from .db import query


def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def init_security(app):
    @app.before_request
    def load_user_and_check_csrf():
        uid = session.get("user_id")
        g.user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True) if uid else None
        if g.user and not g.user["active"]:
            session.clear()
            g.user = None

        if request.method == "POST" and app.config.get("CSRF_ENABLED", True):
            sent = request.form.get("csrf_token", "")
            if not sent or not secrets.compare_digest(sent, session.get("csrf_token", "")):
                abort(400, "Your form expired. Please go back, refresh the page and try again.")

    app.jinja_env.globals["csrf_token"] = get_csrf_token

    @app.context_processor
    def inject_user():
        return {"current_user": g.get("user")}


def login_required(*roles):
    """@login_required() for any user, @login_required('donor') to restrict by role."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login", next=request.path))
            if roles and g.user["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
