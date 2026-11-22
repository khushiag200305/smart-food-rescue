"""Business metrics sent to Amazon CloudWatch (namespace SmartFoodRescue).

Metrics: DonationsPosted, PickupRequests, PickupsCompleted, MealsRescued.
They appear on the CloudWatch dashboard (deploy/cloudwatch-dashboard.json).
Off unless CLOUDWATCH_METRICS=1, so local development never calls AWS.
A failure here is logged and never breaks the page the user is using.
"""
from flask import current_app

from .aws import client

NAMESPACE = "SmartFoodRescue"


def record(name, value=1, unit="Count"):
    if not current_app.config.get("CLOUDWATCH_METRICS"):
        current_app.logger.info("metric=%s value=%s (CloudWatch off locally)", name, value)
        return
    try:
        client("cloudwatch").put_metric_data(
            Namespace=NAMESPACE,
            MetricData=[{"MetricName": name, "Value": value, "Unit": unit}],
        )
    except Exception:
        current_app.logger.exception("metric_failed metric=%s", name)
