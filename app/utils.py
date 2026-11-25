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


STATUS_LABELS = {"available": "Available", "requested": "Requested", "approved": "Approved",
                 "picked_up": "Picked up", "completed": "Completed", "expired": "Expired",
                 "pending": "Waiting for donor", "rejected": "Not approved"}


def badge(status):
    """Small status label, styled by .pill-<status> in static/css/style.css."""
    label = escape(STATUS_LABELS.get(status, str(status).replace("_", " ").capitalize()))
    return Markup(f'<span class="pill pill-{escape(status)}">{label}</span>')


def short_time(dt):
    return dt.strftime("%I:%M %p").lstrip("0")


def pickup_label(value):
    """'Today, 9:00 PM' / 'Tomorrow, 8:30 AM' / '28 Nov, 9:00 PM'."""
    dt = to_dt(value)
    if not dt:
        return ""
    days = (dt.date() - now_local().date()).days
    day = {0: "Today", 1: "Tomorrow", -1: "Yesterday"}.get(days, dt.strftime("%d %b").lstrip("0"))
    return f"{day}, {short_time(dt)}"


def pickup_day(value):
    """'today' / 'tomorrow' / 'yesterday' / '28 Nov' (used in 'Pick up today by')."""
    dt = to_dt(value)
    if not dt:
        return ""
    days = (dt.date() - now_local().date()).days
    return {0: "today", 1: "tomorrow", -1: "yesterday"}.get(days, "on " + dt.strftime("%d %b").lstrip("0"))


def pickup_time(value):
    dt = to_dt(value)
    return short_time(dt) if dt else ""


def minutes_left(value):
    """Whole minutes until a pickup deadline (negative once it has passed)."""
    dt = to_dt(value)
    return int((dt - now_local()).total_seconds() // 60) if dt else 0


def time_fraction(listing):
    """Share of the pickup window still left (1.0 = just posted, 0 = deadline reached)."""
    end, start = to_dt(listing.get("available_until")), to_dt(listing.get("created_at"))
    if not end:
        return 0
    if not start or end <= start:
        return 1 if end > now_local() else 0
    left = (end - now_local()).total_seconds() / (end - start).total_seconds()
    return max(0.0, min(1.0, left))


def time_left_label(minutes):
    if minutes <= 0:
        return "Pickup time has passed"
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        return f"{hours // 24} d {hours % 24} h left"
    return f"{hours} h {mins} min left" if hours else f"{mins} min left"


# Lifecycle shown as a step track on dashboards.
STAGES = [("available", "Listed"), ("requested", "Requested"), ("approved", "Approved"),
          ("picked_up", "Picked up"), ("completed", "Done")]
