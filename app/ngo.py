from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import metrics, notifications
from .db import commit, execute, query
from .security import login_required
from .utils import now_local, now_str, to_dt

bp = Blueprint("ngo", __name__, url_prefix="/ngo")


@bp.route("/")
@login_required("ngo")
def browse():
    location = request.args.get("location", "").strip()
    food_type = request.args.get("food_type", "")
    min_qty = request.args.get("min_qty", type=int)

    sql = ("SELECT f.*, u.organization AS donor_org, u.phone AS donor_phone, "
           "(SELECT status FROM pickup_requests r WHERE r.food_id = f.id AND r.ngo_id = ?) AS my_request "
           "FROM food_listings f JOIN users u ON u.id = f.donor_id "
           "WHERE f.status IN ('available', 'requested') AND f.available_until > ?")
    args = [g.user["id"], now_str()]
    if location:
        sql += " AND f.location LIKE ?"
        args.append(f"%{location}%")
    if food_type in ("veg", "non-veg", "mixed"):
        sql += " AND f.food_type = ?"
        args.append(food_type)
    if min_qty:
        sql += " AND f.quantity >= ?"
        args.append(min_qty)
    sql += " ORDER BY f.available_until ASC"

    return render_template("ngo/browse.html", listings=query(sql, tuple(args)), filters=request.args)


@bp.route("/request/<int:food_id>", methods=["POST"])
@login_required("ngo")
def make_request(food_id):
    if not g.user["is_verified"]:
        flash("Your NGO is awaiting admin verification. You can request food once verified.", "warning")
        return redirect(url_for("ngo.browse"))

    listing = query("SELECT * FROM food_listings WHERE id = ?", (food_id,), one=True)
    if not listing or listing["status"] not in ("available", "requested") or to_dt(listing["available_until"]) <= now_local():
        flash("Sorry, this donation is no longer available.", "warning")
        return redirect(url_for("ngo.browse"))
    if query("SELECT id FROM pickup_requests WHERE food_id = ? AND ngo_id = ?",
             (food_id, g.user["id"]), one=True):
        flash("You have already requested this donation.", "info")
        return redirect(url_for("ngo.browse"))

    now = now_str()
    message = request.form.get("message", "").strip()[:500]
    request_id, _ = execute("INSERT INTO pickup_requests (food_id, ngo_id, message, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'pending', ?, ?)",
            (food_id, g.user["id"], message, now, now), commit=False)
    execute("UPDATE food_listings SET status = 'requested' WHERE id = ? AND status = 'available'",
            (food_id,), commit=False)
    commit()
    current_app.logger.info("event=request_created request_id=%s listing_id=%s ngo_id=%s",
                            request_id, food_id, g.user["id"])
    metrics.record("PickupRequests")
    donor = query("SELECT * FROM users WHERE id = ?", (listing["donor_id"],), one=True)
    notifications.request_received(donor, g.user, listing, message)  # SES email to the donor
    flash("Request sent. The donor will approve or reject it soon.", "success")
    return redirect(url_for("ngo.my_requests"))


@bp.route("/requests")
@login_required("ngo")
def my_requests():
    reqs = query(
        "SELECT r.*, f.food_name, f.quantity, f.location, f.available_until, f.image_key, "
        "f.status AS listing_status, u.organization AS donor_org, u.phone AS donor_phone, u.email AS donor_email "
        "FROM pickup_requests r JOIN food_listings f ON f.id = r.food_id "
        "JOIN users u ON u.id = f.donor_id WHERE r.ngo_id = ? ORDER BY r.created_at DESC",
        (g.user["id"],),
    )
    return render_template("ngo/requests.html", requests=reqs)


@bp.route("/requests/<int:req_id>/picked-up", methods=["POST"])
@login_required("ngo")
def picked_up(req_id):
    req = query("SELECT * FROM pickup_requests WHERE id = ?", (req_id,), one=True)
    if not req:
        abort(404)
    if req["ngo_id"] != g.user["id"]:
        abort(403)
    _, changed = (0, 0)
    if req["status"] == "approved":
        _, changed = execute("UPDATE food_listings SET status = 'picked_up' WHERE id = ? AND status = 'approved'",
                             (req["food_id"],))
    if changed:
        current_app.logger.info("event=picked_up listing_id=%s ngo_id=%s", req["food_id"], g.user["id"])
    flash("Marked as picked up. The donor will confirm completion." if changed
          else "Only approved requests can be marked as picked up.", "success" if changed else "warning")
    return redirect(url_for("ngo.my_requests"))
