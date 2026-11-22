"""Time helpers. Times are stored as local (IST by default) 'YYYY-MM-DD HH:MM:SS'
so the app behaves the same on your laptop and on an EC2 server set to UTC."""
from datetime import datetime, timedelta, timezone

from flask import current_app
from markupsafe import Markup, escape

FMT = "%Y-%m-%d %H:%M:%S"


def now_local():
    offset = timedelta(minutes=current_app.config["UTC_OFFSET_MINUTES"])
    return datetime.now(timezone(offset)).replace(tzinfo=None)


def now_str():
    return now_local().strftime(FMT)


def to_dt(value):
    if value is None or isinstance(value, datetime):
        return value
    return datetime.strptime(str(value)[:19], FMT)


def parse_form_datetime(value):
    """HTML <input type=datetime-local> sends '2026-10-12T21:30'."""
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


def fmt_dt(value):
    dt = to_dt(value)
    return dt.strftime("%d %b %Y, %I:%M %p") if dt else ""


def is_expired(listing):
    return listing["status"] in ("available", "requested") and to_dt(listing["available_until"]) < now_local()


BADGE_COLORS = {"available": "success", "requested": "warning", "approved": "primary", "picked_up": "info",
                "completed": "secondary", "expired": "dark", "pending": "warning", "rejected": "danger"}


def badge(status):
    """Bootstrap badge for a listing or request status."""
    label = escape(str(status).replace("_", " ").capitalize())
    return Markup(f'<span class="badge text-bg-{BADGE_COLORS.get(status, "light")}">{label}</span>')
