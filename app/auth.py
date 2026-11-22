from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import execute, query
from .storage import DOC_EXTENSIONS, allowed_file, upload_file
from .utils import now_str

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, email = f.get("name", "").strip(), f.get("email", "").strip().lower()
        password, role = f.get("password", ""), f.get("role", "")
        organization, phone = f.get("organization", "").strip(), f.get("phone", "").strip()
        doc = request.files.get("verification_doc")

        error = None
        if not name or not email or not organization:
            error = "Name, email and organisation are required."
        elif role not in ("donor", "ngo"):
            error = "Choose whether you are a donor or an NGO."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif query("SELECT id FROM users WHERE email = ?", (email,), one=True):
            error = "An account with this email already exists."
        elif role == "ngo" and (not doc or not doc.filename):
            error = "NGOs must upload a registration certificate (PDF or image) for verification."
        elif role == "ngo" and not allowed_file(doc.filename, DOC_EXTENSIONS):
            error = "Certificate must be a PDF, PNG, JPG or WEBP file."

        if error:
            flash(error, "danger")
            return render_template("auth/register.html", form=f)

        doc_key = upload_file(doc, folder="ngo-docs") if role == "ngo" else None
        execute(
            "INSERT INTO users (name, email, password_hash, role, organization, phone, "
            "verification_doc_key, is_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, email, generate_password_hash(password), role, organization, phone,
             doc_key, 1 if role == "donor" else 0, now_str()),
        )
        current_app.logger.info("event=user_registered role=%s email=%s", role, email)
        msg = "Account created. Please log in."
        if role == "ngo":
            msg += " An admin will verify your NGO before you can request food."
        flash(msg, "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            current_app.logger.warning("event=login_failed email=%s ip=%s", email, request.remote_addr)
            flash("Incorrect email or password.", "danger")
        elif not user["active"]:
            flash("This account has been deactivated by the admin.", "danger")
        else:
            session.clear()
            session["user_id"] = user["id"]
            current_app.logger.info("event=login user_id=%s role=%s", user["id"], user["role"])
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("main.dashboard"))
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))
