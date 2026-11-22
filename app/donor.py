from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for

from . import metrics, notifications
from .db import commit, execute, query
from .security import login_required
from .storage import allowed_file, delete_file, upload_file
from .utils import FMT, now_local, now_str, parse_form_datetime

bp = Blueprint("donor", __name__, url_prefix="/donor")


def own_listing(food_id):
    listing = query("SELECT * FROM food_listings WHERE id = ?", (food_id,), one=True)
    if not listing:
        abort(404)
    if listing["donor_id"] != g.user["id"]:
        abort(403)
    return listing


@bp.route("/")
@login_required("donor")
def dashboard():
    listings = query(
        "SELECT * FROM food_listings WHERE donor_id = ? ORDER BY created_at DESC", (g.user["id"],)
    )
    reqs = query(
        "SELECT r.*, u.name AS ngo_name, u.organization AS ngo_org, u.phone AS ngo_phone, u.email AS ngo_email "
        "FROM pickup_requests r JOIN users u ON u.id = r.ngo_id "
        "JOIN food_listings f ON f.id = r.food_id WHERE f.donor_id = ? ORDER BY r.created_at",
        (g.user["id"],),
    )
    by_listing = {}
    for r in reqs:
        by_listing.setdefault(r["food_id"], []).append(r)
    return render_template("donor/dashboard.html", listings=listings, requests=by_listing)


@bp.route("/new", methods=["GET", "POST"])
@login_required("donor")
def new_listing():
    if request.method == "POST":
        f = request.form
        image = request.files.get("image")
        until = parse_form_datetime(f.get("available_until"))
        try:
            quantity = int(f.get("quantity", 0))
        except ValueError:
            quantity = 0

        error = None
        if not f.get("food_name", "").strip() or not f.get("location", "").strip():
            error = "Food name and pickup location are required."
        elif quantity <= 0:
            error = "Quantity must be a positive number of meals."
        elif f.get("food_type") not in ("veg", "non-veg", "mixed"):
            error = "Choose a food type."
        elif not until or until <= now_local():
            error = "'Available until' must be a time in the future."
        elif not image or not image.filename:
            error = "Please add a photo of the food."
        elif not allowed_file(image.filename) or not (image.mimetype or "").startswith("image/"):
            error = "Photo must be a PNG, JPG or WEBP image."

        if error:
            flash(error, "danger")
            return render_template("donor/new_listing.html", form=f)

        key = upload_file(image, folder="food")
        listing_id, _ = execute(
            "INSERT INTO food_listings (donor_id, food_name, food_type, quantity, location, "
            "description, image_key, available_until, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'available', ?)",
            (g.user["id"], f["food_name"].strip(), f["food_type"], quantity, f["location"].strip(),
             f.get("description", "").strip(), key, until.strftime(FMT), now_str()),
        )
        listing = query("SELECT * FROM food_listings WHERE id = ?", (listing_id,), one=True)
        current_app.logger.info("event=listing_created listing_id=%s donor_id=%s meals=%s",
                                listing_id, g.user["id"], quantity)
        metrics.record("DonationsPosted")
        notifications.new_food_alert(listing, g.user)  # SNS: one publish -> all subscribed NGOs
        flash("Donation listed. NGOs can now see it.", "success")
        return redirect(url_for("donor.dashboard"))

    return render_template("donor/new_listing.html", form={})


@bp.route("/request/<int:req_id>/<action>", methods=["POST"])
@login_required("donor")
def decide_request(req_id, action):
    if action not in ("approve", "reject"):
        abort(404)
    req = query("SELECT * FROM pickup_requests WHERE id = ?", (req_id,), one=True)
    if not req:
        abort(404)
    listing = own_listing(req["food_id"])
    if req["status"] != "pending":
        flash("This request has already been handled.", "warning")
        return redirect(url_for("donor.dashboard"))

    def ngo_of(r):
        return query("SELECT * FROM users WHERE id = ?", (r["ngo_id"],), one=True)

    now = now_str()
    if action == "approve":
        others = query("SELECT * FROM pickup_requests WHERE food_id = ? AND id <> ? AND status = 'pending'",
                       (listing["id"], req_id))
        # Conditional update: only one request can ever win the listing.
        _, changed = execute(
            "UPDATE food_listings SET status = 'approved' WHERE id = ? AND status IN ('available', 'requested')",
            (listing["id"],), commit=False,
        )
        if not changed:
            flash("This donation is no longer available.", "warning")
            return redirect(url_for("donor.dashboard"))
        execute("UPDATE pickup_requests SET status = 'approved', updated_at = ? WHERE id = ?",
                (now, req_id), commit=False)
        execute("UPDATE pickup_requests SET status = 'rejected', updated_at = ? "
                "WHERE food_id = ? AND id <> ? AND status = 'pending'",
                (now, listing["id"], req_id), commit=False)
        commit()
        current_app.logger.info("event=request_approved request_id=%s listing_id=%s auto_declined=%s",
                                req_id, listing["id"], len(others))
        notifications.request_decided(ngo_of(req), listing, g.user, approved=True)  # SES
        for other in others:
            notifications.request_decided(ngo_of(other), listing, g.user, approved=False)
        flash("Request approved. Other pending requests were declined automatically.", "success")
    else:
        execute("UPDATE pickup_requests SET status = 'rejected', updated_at = ? WHERE id = ?",
                (now, req_id), commit=False)
        pending = query("SELECT COUNT(*) AS n FROM pickup_requests WHERE food_id = ? AND status = 'pending'",
                        (listing["id"],), one=True)["n"]
        if pending == 0:
            execute("UPDATE food_listings SET status = 'available' WHERE id = ? AND status = 'requested'",
                    (listing["id"],), commit=False)
        commit()
        current_app.logger.info("event=request_rejected request_id=%s listing_id=%s", req_id, listing["id"])
        notifications.request_decided(ngo_of(req), listing, g.user, approved=False)  # SES
        flash("Request rejected.", "info")
    return redirect(url_for("donor.dashboard"))


@bp.route("/listing/<int:food_id>/complete", methods=["POST"])
@login_required("donor")
def complete(food_id):
    listing = own_listing(food_id)
    _, changed = execute("UPDATE food_listings SET status = 'completed' WHERE id = ? AND status = 'picked_up'",
                         (listing["id"],))
    if changed:
        current_app.logger.info("event=donation_completed listing_id=%s meals=%s",
                                listing["id"], listing["quantity"])
        metrics.record("PickupsCompleted")
        metrics.record("MealsRescued", listing["quantity"])
    flash("Donation marked as completed. Thank you!" if changed
          else "Only picked-up donations can be completed.", "success" if changed else "warning")
    return redirect(url_for("donor.dashboard"))


@bp.route("/listing/<int:food_id>/delete", methods=["POST"])
@login_required("donor")
def delete(food_id):
    listing = own_listing(food_id)
    if listing["status"] not in ("available", "requested", "expired"):
        flash("Approved or completed donations can't be deleted.", "warning")
        return redirect(url_for("donor.dashboard"))
    execute("DELETE FROM food_listings WHERE id = ?", (listing["id"],))
    delete_file(listing["image_key"])
    current_app.logger.info("event=listing_deleted listing_id=%s donor_id=%s", listing["id"], g.user["id"])
    flash("Listing deleted.", "info")
    return redirect(url_for("donor.dashboard"))
