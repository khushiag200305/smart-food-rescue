from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, url_for

from . import notifications
from .db import execute, query
from .main import platform_stats
from .security import login_required
from .storage import delete_file

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@login_required("admin")
def dashboard():
    stats = platform_stats()
    stats["pending_ngos"] = query(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'ngo' AND is_verified = 0", one=True)["n"]
    by_status = query("SELECT status, COUNT(*) AS n FROM food_listings GROUP BY status")
    users = query("SELECT * FROM users ORDER BY role, created_at DESC")
    listings = query(
        "SELECT f.*, u.organization AS donor_org FROM food_listings f "
        "JOIN users u ON u.id = f.donor_id ORDER BY f.created_at DESC"
    )
    return render_template("admin/dashboard.html", stats=stats, by_status=by_status,
                           users=users, listings=listings)


@bp.route("/users/<int:user_id>/verify", methods=["POST"])
@login_required("admin")
def verify(user_id):
    _, changed = execute("UPDATE users SET is_verified = 1 WHERE id = ? AND role = 'ngo' AND is_verified = 0",
                         (user_id,))
    if changed:
        ngo = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
        current_app.logger.info("event=ngo_verified user_id=%s admin_id=%s", user_id, g.user["id"])
        notifications.ngo_verified(ngo)  # SES email + SNS food-alert subscription
        flash("NGO verified. They've been emailed and subscribed to food alerts.", "success")
    else:
        flash("This NGO is already verified, or wasn't found.", "warning")
    return redirect(url_for("admin.dashboard"))


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@login_required("admin")
def toggle_active(user_id):
    if user_id == g.user["id"]:
        flash("You can't deactivate your own account.", "warning")
        return redirect(url_for("admin.dashboard"))
    user = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        abort(404)
    execute("UPDATE users SET active = ? WHERE id = ?", (0 if user["active"] else 1, user_id))
    flash(f"{user['name']} {'deactivated' if user['active'] else 'reactivated'}.", "info")
    return redirect(url_for("admin.dashboard"))


@bp.route("/listings/<int:food_id>/remove", methods=["POST"])
@login_required("admin")
def remove_listing(food_id):
    listing = query("SELECT * FROM food_listings WHERE id = ?", (food_id,), one=True)
    if not listing:
        abort(404)
    execute("DELETE FROM food_listings WHERE id = ?", (food_id,))
    delete_file(listing["image_key"])
    flash("Listing removed.", "info")
    return redirect(url_for("admin.dashboard"))
