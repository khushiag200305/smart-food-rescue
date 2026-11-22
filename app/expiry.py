"""Expire food listings whose pickup window has passed.

Shared by two callers so the logic lives in one place:
  * AWS Lambda (lambda/expire_listings/), run every 15 minutes by EventBridge Scheduler
  * the local command  `flask --app run expire-listings`  for development without AWS

It must not import Flask: the Lambda package contains only this file, the handler and PyMySQL.
"""
from datetime import datetime, timedelta, timezone

FMT = "%Y-%m-%d %H:%M:%S"


def local_now(utc_offset_minutes):
    """Current time in the app's timezone (IST by default), as stored in the database.

    Lambda runs in UTC, so the offset must be applied explicitly."""
    tz = timezone(timedelta(minutes=utc_offset_minutes))
    return datetime.now(tz).replace(tzinfo=None).strftime(FMT)


def expire_listings(conn, now, placeholder="%s"):
    """Mark overdue listings as expired and decline their pending requests.

    conn        an open DB-API connection (PyMySQL on AWS, sqlite3 locally)
    now         current local time as 'YYYY-MM-DD HH:MM:SS'
    placeholder '%s' for MySQL, '?' for SQLite
    Returns a dict with the number of listings expired and requests declined.
    """
    p = placeholder
    overdue = f"status IN ('available', 'requested') AND available_until < {p}"
    cur = conn.cursor()
    try:
        # 1. Decline pending requests for listings that are about to expire.
        cur.execute(
            f"UPDATE pickup_requests SET status = 'rejected', updated_at = {p} "
            f"WHERE status = 'pending' AND food_id IN (SELECT id FROM food_listings WHERE {overdue})",
            (now, now),
        )
        requests_declined = cur.rowcount
        # 2. Expire the listings themselves.
        cur.execute(f"UPDATE food_listings SET status = 'expired' WHERE {overdue}", (now,))
        listings_expired = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
    return {"listings_expired": listings_expired, "requests_declined": requests_declined}
