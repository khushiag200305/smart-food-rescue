"""Smart Food Rescue — Flask application factory."""
import logging
import os

from dotenv import load_dotenv
from flask import Flask, flash, redirect, request


def create_app(test_config=None):
    load_dotenv()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
        # Local default: SQLite file. On AWS: mysql://user:pass@<rds-endpoint>:3306/smart_food_rescue
        DATABASE_URL=os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(base_dir, "local.db")),
        # Leave S3_BUCKET empty locally -> images are saved to ./uploads instead.
        S3_BUCKET=os.environ.get("S3_BUCKET") or None,
        AWS_REGION=os.environ.get("AWS_REGION", "ap-southeast-2"),
        LOCAL_UPLOAD_DIR=os.path.join(base_dir, "uploads"),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,  # 5 MB upload limit
        UTC_OFFSET_MINUTES=int(os.environ.get("UTC_OFFSET_MINUTES", 330)),  # IST
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
        CSRF_ENABLED=True,
        # --- Notifications (leave empty locally: emails are logged instead of sent) ---
        SNS_TOPIC_ARN=os.environ.get("SNS_TOPIC_ARN") or None,  # food alerts to all NGOs
        SES_SENDER=os.environ.get("SES_SENDER") or None,        # verified "from" address
        # --- CloudWatch ---
        CLOUDWATCH_METRICS=os.environ.get("CLOUDWATCH_METRICS", "0") == "1",
        LOG_FILE=os.environ.get("LOG_FILE") or None,  # e.g. /var/log/smartfood/app.log on EC2
    )
    if test_config:
        app.config.update(test_config)

    configure_logging(app)

    from . import db
    db.init_app(app)

    from .demo import register_demo_command
    register_demo_command(app)

    from .security import init_security
    init_security(app)

    from .storage import file_url
    from .utils import badge, fmt_dt, is_expired
    app.jinja_env.globals.update(file_url=file_url, is_expired=is_expired, badge=badge)
    app.jinja_env.filters["dt"] = fmt_dt

    from .admin import bp as admin_bp
    from .auth import bp as auth_bp
    from .donor import bp as donor_bp
    from .main import bp as main_bp
    from .ngo import bp as ngo_bp
    for bp in (main_bp, auth_bp, donor_bp, ngo_bp, admin_bp):
        app.register_blueprint(bp)

    @app.errorhandler(413)
    def too_large(_e):
        flash("File is too large. The limit is 5 MB.", "danger")
        return redirect(request.referrer or "/")

    return app


def configure_logging(app):
    """App events go to the terminal, and on EC2 also to LOG_FILE, which the
    CloudWatch agent ships to CloudWatch Logs (log group /smartfood/app)."""
    from flask.logging import default_handler

    app.logger.removeHandler(default_handler)  # replaced by the handlers below
    app.logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    if not any(getattr(h, "_smartfood", False) for h in app.logger.handlers):
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console._smartfood = True
        app.logger.addHandler(console)
        if app.config.get("LOG_FILE"):
            file_handler = logging.FileHandler(app.config["LOG_FILE"])
            file_handler.setFormatter(fmt)
            file_handler._smartfood = True
            app.logger.addHandler(file_handler)
    app.logger.propagate = False
