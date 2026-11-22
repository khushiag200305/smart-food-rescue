from flask import Blueprint, abort, current_app, g, redirect, render_template, send_from_directory, url_for

from .db import query
from .security import login_required

bp = Blueprint("main", __name__)


def platform_stats():
    row = query(
        "SELECT COUNT(*) AS total_listings, "
        "COALESCE(SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END), 0) AS completed, "
        "COALESCE(SUM(CASE WHEN status = 'completed' THEN quantity ELSE 0 END), 0) AS meals "
        "FROM food_listings",
        one=True,
    )
    row["ngos"] = query("SELECT COUNT(*) AS n FROM users WHERE role = 'ngo'", one=True)["n"]
    row["donors"] = query("SELECT COUNT(*) AS n FROM users WHERE role = 'donor'", one=True)["n"]
    return row


@bp.route("/")
def index():
    return render_template("index.html", stats=platform_stats())


@bp.route("/dashboard")
@login_required()
def dashboard():
    target = {"donor": "donor.dashboard", "ngo": "ngo.browse", "admin": "admin.dashboard"}
    return redirect(url_for(target[g.user["role"]]))


@bp.route("/uploads/<path:key>")
@login_required()
def uploaded_file(key):
    """Serves local uploads during development only (S3 is used in the cloud)."""
    if current_app.config.get("S3_BUCKET"):
        abort(404)
    return send_from_directory(current_app.config["LOCAL_UPLOAD_DIR"], key)
