"""Tiny database layer: plain SQL on SQLite (local) or MySQL (AWS RDS).

Write queries with `?` placeholders; they are converted to `%s` for MySQL.
"""
import os
import sqlite3
from urllib.parse import unquote, urlparse

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        url = current_app.config["DATABASE_URL"]
        if url.startswith("mysql"):
            import pymysql  # only needed when talking to RDS

            u = urlparse(url)
            g.db = pymysql.connect(
                host=u.hostname,
                port=u.port or 3306,
                user=unquote(u.username or ""),
                password=unquote(u.password or ""),
                database=u.path.lstrip("/"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
            )
            g.db_kind = "mysql"
        else:
            g.db = sqlite3.connect(url.replace("sqlite:///", "", 1))
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
            g.db_kind = "sqlite"
    return g.db


def _sql(q):
    return q.replace("?", "%s") if g.db_kind == "mysql" else q


def query(sql, args=(), one=False):
    """Run a SELECT and return a list of dicts (or one dict / None)."""
    cur = get_db().cursor()
    cur.execute(_sql(sql), args)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, args=(), commit=True):
    """Run INSERT/UPDATE/DELETE. Returns (lastrowid, rowcount)."""
    db = get_db()
    cur = db.cursor()
    cur.execute(_sql(sql), args)
    result = (cur.lastrowid, cur.rowcount)
    cur.close()
    if commit:
        db.commit()
    return result


def commit():
    get_db().commit()


def rollback():
    get_db().rollback()


def close_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_schema():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    db = get_db()
    if g.db_kind == "sqlite":
        with open(os.path.join(root, "schema_sqlite.sql")) as f:
            db.executescript(f.read())
    else:
        with open(os.path.join(root, "schema.sql")) as f:
            lines = [ln for ln in f if not ln.strip().startswith("--")]
        cur = db.cursor()
        for stmt in "".join(lines).split(";"):
            if stmt.strip():
                cur.execute(stmt)
        cur.close()
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():
        """Create all tables (safe to run twice)."""
        init_schema()
        click.echo("Database tables created.")

    @app.cli.command("expire-listings")
    def expire_listings_command():
        """Run the listing-expiry job locally (on AWS, the Lambda function does this)."""
        from .expiry import expire_listings
        from .utils import now_str
        conn = get_db()
        result = expire_listings(conn, now_str(), placeholder="%s" if g.db_kind == "mysql" else "?")
        click.echo(f"Expired {result['listings_expired']} listing(s), "
                   f"declined {result['requests_declined']} pending request(s).")

    @app.cli.command("create-admin")
    @click.argument("email")
    @click.argument("password")
    @click.option("--name", default="Admin")
    def create_admin_command(email, password, name):
        """Create an admin account: flask --app run create-admin you@x.com secret"""
        from .utils import now_str
        execute(
            "INSERT INTO users (name, email, password_hash, role, is_verified, created_at) "
            "VALUES (?, ?, ?, 'admin', 1, ?)",
            (name, email.lower(), generate_password_hash(password), now_str()),
        )
        click.echo(f"Admin {email} created.")
