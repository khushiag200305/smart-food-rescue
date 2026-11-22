"""Demo data for presentations:  flask --app run seed-demo  [--reset]

Creates donors, NGOs, an admin, and food listings at every stage of the lifecycle
(available -> requested -> approved -> picked up -> completed), with photos.
Photos go through the normal upload code, so on EC2 they land in your S3 bucket.

Want real photos? Replace files in demo_data/photos/ with your own pictures
using the same names (e.g. rice_dal.jpg, or rice_dal.png) and re-run with --reset.
"""
import os
from datetime import timedelta

import click
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash

from .db import execute, query
from .storage import delete_file, upload_file
from .utils import FMT, now_local

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "demo_data"))
PASSWORD = "Demo@1234"

# key: (name, email, role, organization, phone, certificate, verified)
USERS = {
    "admin":         ("Platform Admin", "admin@demo.in", "admin", "Smart Food Rescue", "", None, 1),
    "mess":          ("Ravinder Singh", "mess@demo.in", "donor", "Hostel J Mess", "98140 11111", None, 1),
    "spiceroute":    ("Neha Kapoor", "spiceroute@demo.in", "donor", "Spice Route Restaurant", "98140 22222", None, 1),
    "royalpalms":    ("Arjun Mehta", "royalpalms@demo.in", "donor", "Hotel Royal Palms", "98140 33333", None, 1),
    "greenleaf":     ("Simran Kaur", "greenleaf@demo.in", "donor", "Green Leaf Cafeteria", "98140 44444", None, 1),
    "rotighar":      ("Asha Verma", "rotighar@demo.in", "ngo", "Roti Ghar Foundation", "98150 55555", "roti_ghar", 1),
    "helpinghands":  ("Mohit Sharma", "helpinghands@demo.in", "ngo", "Helping Hands Patiala", "98150 66666", "helping_hands", 1),
    "annapurna":     ("Kavita Rani", "annapurna@demo.in", "ngo", "Annapurna Seva Trust", "98150 77777", "annapurna", 0),
}

LOCATIONS = {
    "mess": "Hostel J Mess, University Campus, Patiala",
    "spiceroute": "Spice Route Restaurant, Leela Bhawan, Patiala",
    "royalpalms": "Hotel Royal Palms, The Mall, Patiala",
    "greenleaf": "Green Leaf Cafeteria, Urban Estate Phase 2, Patiala",
}

# (food, type, meals, donor, photo, status, available_until_hours, created_hours, description,
#  [(ngo, request_status, message), ...])
LISTINGS = [
    ("Rice and dal", "veg", 40, "mess", "rice_dal", "available", 3, -0.5,
     "Dinner surplus, cooked at 7 PM. Packed in steel containers; please bring your own vessels.", []),
    ("Veg sandwiches", "veg", 30, "greenleaf", "veg_sandwiches", "available", 5, -1,
     "Freshly made this evening, individually wrapped.", []),
    ("Fresh fruit platter", "veg", 15, "royalpalms", "fruit_platter", "available", 2, -0.3,
     "Cut fruit from a banquet buffet. Best collected within two hours.", []),
    ("Veg biryani", "veg", 60, "royalpalms", "veg_biryani", "requested", 4, -1.5,
     "Wedding banquet surplus. Untouched, kept in hot cases.",
     [("rotighar", "pending", "We can reach in 40 minutes with our van."),
      ("helpinghands", "pending", "Can collect by 10 PM for the night shelter.")]),
    ("Paneer butter masala with rotis", "veg", 25, "spiceroute", "paneer_butter_masala", "requested", 3, -1,
     "Prepared for a cancelled party order.",
     [("rotighar", "pending", "Our volunteer is nearby and can pick up in 20 minutes.")]),
    # Already past its pickup time: the expiry job (Lambda, or `flask expire-listings`) will expire it.
    ("Jeera rice and dal", "veg", 20, "greenleaf", "rice_dal", "requested", -0.5, -4,
     "Lunch surplus from the cafeteria.",
     [("helpinghands", "pending", "Can we collect after 6 PM?")]),
    ("Rajma chawal", "veg", 50, "mess", "rajma_chawal", "approved", 2, -3,
     "Lunch surplus kept refrigerated.",
     [("helpinghands", "approved", "Will collect at 4 PM."),
      ("rotighar", "rejected", "Need it for the evening distribution.")]),
    ("Chicken curry", "non-veg", 20, "spiceroute", "chicken_curry", "picked_up", 1, -4,
     "Packed in sealed containers.",
     [("rotighar", "approved", "Collecting now.")]),
    ("Roti and mixed sabzi", "veg", 45, "mess", "roti_sabzi", "completed", -20, -24,
     "Dinner surplus.", [("helpinghands", "approved", "Picking up for the slum school.")]),
    ("Idli sambar", "veg", 35, "greenleaf", "idli_sambar", "completed", -44, -48,
     "Breakfast surplus.", [("rotighar", "approved", "On our way.")]),
    ("Poha", "veg", 30, "mess", "poha", "completed", -68, -72,
     "Breakfast surplus.", [("rotighar", "approved", "Will collect at 10 AM.")]),
    ("Veg biryani", "veg", 80, "royalpalms", "veg_biryani", "completed", -92, -96,
     "Conference lunch surplus.", [("helpinghands", "approved", "Sending two volunteers.")]),
    ("Rice and dal", "veg", 55, "mess", "rice_dal", "completed", -116, -120,
     "Dinner surplus.", [("rotighar", "approved", "Thank you!")]),
]


def _find(folder, stem):
    for ext in ("jpg", "jpeg", "png", "webp"):
        path = os.path.join(ROOT, folder, f"{stem}.{ext}")
        if os.path.exists(path):
            return path, ext
    raise click.ClickException(f"Missing demo file: demo_data/{folder}/{stem}.jpg")


def _upload(folder, stem, s3_folder):
    path, ext = _find(folder, stem)
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    with open(path, "rb") as fh:
        return upload_file(FileStorage(stream=fh, filename=os.path.basename(path), content_type=mime), s3_folder)


def _t(hours):
    return (now_local() + timedelta(hours=hours)).strftime(FMT)


def _reset():
    for row in query("SELECT image_key FROM food_listings"):
        delete_file(row["image_key"])
    for row in query("SELECT verification_doc_key FROM users"):
        delete_file(row["verification_doc_key"])
    execute("DELETE FROM pickup_requests")
    execute("DELETE FROM food_listings")
    execute("DELETE FROM users")


def register_demo_command(app):
    @app.cli.command("seed-demo")
    @click.option("--reset", is_flag=True, help="Delete ALL existing users, listings and files first.")
    def seed_demo(reset):
        """Fill the database with realistic demo data and photos."""
        if reset:
            _reset()
            click.echo("Existing data removed.")
        elif query("SELECT id FROM users LIMIT 1"):
            raise click.ClickException("Database already has users. Re-run with --reset to replace everything.")

        ids, pw = {}, generate_password_hash(PASSWORD)
        for key, (name, email, role, org, phone, cert, verified) in USERS.items():
            doc = _upload("certificates", cert, "ngo-docs") if cert else None
            ids[key], _ = execute(
                "INSERT INTO users (name, email, password_hash, role, organization, phone, "
                "verification_doc_key, is_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, email, pw, role, org, phone, doc, verified, _t(-24 * 10)),
            )

        for food, ftype, qty, donor, photo, status, until_h, created_h, desc, reqs in LISTINGS:
            food_id, _ = execute(
                "INSERT INTO food_listings (donor_id, food_name, food_type, quantity, location, description, "
                "image_key, available_until, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (ids[donor], food, ftype, qty, LOCATIONS[donor], desc, _upload("photos", photo, "food"),
                 _t(until_h), status, _t(created_h)),
            )
            for i, (ngo, rstatus, msg) in enumerate(reqs):
                execute(
                    "INSERT INTO pickup_requests (food_id, ngo_id, message, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (food_id, ids[ngo], msg, rstatus, _t(created_h + 0.2 + i * 0.1), _t(created_h + 0.5)),
                )

        meals = sum(item[2] for item in LISTINGS if item[5] == "completed")
        click.echo(f"Created {len(USERS)} users and {len(LISTINGS)} listings ({meals} meals already donated).\n")
        click.echo(f"All demo accounts use the password: {PASSWORD}")
        for key, (_n, email, role, org, *_rest) in USERS.items():
            note = " (unverified: use to demo admin verification)" if key == "annapurna" else ""
            click.echo(f"  {role:<6} {email:<24} {org}{note}")
        click.echo("\nOne listing (Jeera rice and dal) is already overdue: the expiry Lambda,\n"
                   "or `flask --app run expire-listings` locally, will mark it expired.")
